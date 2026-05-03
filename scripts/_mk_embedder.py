#!/usr/bin/env python3
"""Generate services/daily_pool/embedder.py"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "services", "daily_pool", "embedder.py")

B1 = chr(123)  # {
B2 = chr(125)  # }

src = f'''# -*- coding: utf-8 -*-
"""
Embedder service: generates embeddings and checks deduplication.
Threshold: cosine similarity < 0.85 against last 365 days of same combination.
"""
import hashlib
import logging
import math
import struct
from datetime import datetime, timedelta, timezone

from services.openrouter_client import openrouter

logger = logging.getLogger(__name__)

MODEL = "openai/text-embedding-3-large"
SIMILARITY_THRESHOLD = 0.85
LOOKBACK_DAYS = 365
EMBEDDING_DIM = 3072


def _cosine_similarity(a: list, b: list) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _embedding_to_bytes(embedding: list) -> bytes:
    """Pack embedding as binary (for SQLite BLOB storage)."""
    fmt = str(len(embedding)) + 'f'
    return struct.pack(fmt, *embedding)


def _bytes_to_embedding(data: bytes) -> list:
    """Unpack embedding from binary."""
    count = len(data) // 4
    fmt = str(count) + 'f'
    return list(struct.unpack(fmt, data))


def get_embedding(text: str) -> list:
    """Get embedding vector for a text string."""
    truncated = text[:32000]
    embedding = openrouter.embed(truncated, model=MODEL)
    token_estimate = len(truncated) // 4
    cost_estimate = token_estimate * 0.13 / 1_000_000
    openrouter.log_cost_to_db(
        'embed', MODEL,
        dict(prompt_tokens=token_estimate, completion_tokens=0),
        cost_estimate
    )
    return embedding


def check_deduplication(
    statement: str,
    olympiad_slug: str,
    grade: int,
    round_name: str,
    use_pgvector: bool = False,
) -> dict:
    """
    Check if a problem statement is too similar to existing problems.

    Args:
        statement: Problem statement text
        olympiad_slug: e.g. 'vsosh'
        grade: e.g. 9
        round_name: e.g. 'regional'
        use_pgvector: If True, use pgvector cosine distance (PostgreSQL only)

    Returns dict with:
        is_duplicate: bool
        max_similarity: float
        similar_problem_id: int or None
        embedding: list (3072 floats)
    """
    embedding = get_embedding(statement)

    cutoff_date = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)

    if use_pgvector:
        result = _check_pgvector(embedding, olympiad_slug, grade, round_name, cutoff_date)
    else:
        result = _check_brute_force(embedding, olympiad_slug, grade, round_name, cutoff_date)

    result["embedding"] = embedding
    logger.info(
        f"[Embedder] {B1}olympiad_slug{B2}/{B1}grade{B2}/{B1}round_name{B2} "
        f"max_sim={B1}result['max_similarity']:.3f{B2} dup={B1}result['is_duplicate']{B2}"
    )
    return result


def _check_pgvector(
    embedding: list,
    olympiad_slug: str,
    grade: int,
    round_name: str,
    cutoff_date: datetime,
) -> dict:
    """Use pgvector cosine distance operator for efficient similarity search."""
    from models import db

    embedding_literal = '[' + ','.join(str(x) for x in embedding) + ']'

    row = db.session.execute(
        db.text("""
            SELECT id, 1 - (embedding <=> :vec::vector) AS similarity
            FROM problem_embeddings
            WHERE olympiad_slug = :slug
              AND grade = :grade
              AND round = :round
              AND created_at >= :cutoff
            ORDER BY embedding <=> :vec::vector
            LIMIT 1
        """),
        dict(
            vec=embedding_literal,
            slug=olympiad_slug,
            grade=grade,
            round=round_name,
            cutoff=cutoff_date,
        )
    ).fetchone()

    if row is None:
        return dict(
            is_duplicate=False,
            max_similarity=0.0,
            similar_problem_id=None,
        )

    similarity = float(row[1])
    return dict(
        is_duplicate=similarity >= SIMILARITY_THRESHOLD,
        max_similarity=round(similarity, 4),
        similar_problem_id=row[0] if similarity >= SIMILARITY_THRESHOLD else None,
    )


def _check_brute_force(
    embedding: list,
    olympiad_slug: str,
    grade: int,
    round_name: str,
    cutoff_date: datetime,
) -> dict:
    """Brute-force cosine similarity check (SQLite fallback)."""
    from models import db

    rows = db.session.execute(
        db.text("""
            SELECT id, embedding
            FROM problem_embeddings
            WHERE olympiad_slug = :slug
              AND grade = :grade
              AND round = :round
              AND created_at >= :cutoff
        """),
        dict(
            slug=olympiad_slug,
            grade=grade,
            round=round_name,
            cutoff=cutoff_date.isoformat(),
        )
    ).fetchall()

    max_sim = 0.0
    max_id = None

    for row in rows:
        stored_emb = _bytes_to_embedding(row[1])
        sim = _cosine_similarity(embedding, stored_emb)
        if sim > max_sim:
            max_sim = sim
            max_id = row[0]

    return dict(
        is_duplicate=max_sim >= SIMILARITY_THRESHOLD,
        max_similarity=round(max_sim, 4),
        similar_problem_id=max_id if max_sim >= SIMILARITY_THRESHOLD else None,
    )


def save_embedding(
    problem_id: int,
    statement: str,
    olympiad_slug: str,
    grade: int,
    round_name: str,
    embedding: list,
    use_pgvector: bool = False,
):
    """Save embedding to problem_embeddings table."""
    from models import db

    if use_pgvector:
        embedding_val = '[' + ','.join(str(x) for x in embedding) + ']'
        db.session.execute(
            db.text("""
                INSERT INTO problem_embeddings
                    (problem_id, statement_hash, olympiad_slug, grade, round, embedding)
                VALUES (:pid, md5(:stmt), :slug, :grade, :round, :emb::vector)
            """),
            dict(
                pid=problem_id,
                stmt=statement,
                slug=olympiad_slug,
                grade=grade,
                round=round_name,
                emb=embedding_val,
            )
        )
    else:
        emb_bytes = _embedding_to_bytes(embedding)
        stmt_hash = hashlib.md5(statement.encode()).hexdigest()
        db.session.execute(
            db.text("""
                INSERT INTO problem_embeddings
                    (problem_id, statement_hash, olympiad_slug, grade, round, embedding)
                VALUES (:pid, :hash, :slug, :grade, :round, :emb)
            """),
            dict(
                pid=problem_id,
                hash=stmt_hash,
                slug=olympiad_slug,
                grade=grade,
                round=round_name,
                emb=emb_bytes,
            )
        )

    db.session.commit()
    logger.info(f'[Embedder] Saved embedding for problem {B1}problem_id{B2}')
'''

with open(path, 'w', encoding='utf-8') as f:
    f.write(src)
print(f"Written: {path} ({len(src)} bytes)")
