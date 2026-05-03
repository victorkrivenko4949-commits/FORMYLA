#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate embedder.py, polisher.py, meta_reviewer.py for services/daily_pool/
Run: python scripts/_gen_pipeline.py
"""
import os
import textwrap

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "services", "daily_pool")
LB = "{"
RB = "}"


def main():
    write_embedder()
    write_polisher()
    write_meta_reviewer()
    print("All 3 pipeline services generated successfully.")


def write_embedder():
    # Using textwrap.dedent and format to inject braces
    code = textwrap.dedent(f'''
        # -*- coding: utf-8 -*-
        """
        Embedder service: generates embeddings and checks deduplication.
        Threshold: cosine similarity < 0.85 against last 365 days of same combination.
        """
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
            return struct.pack(f'{LB}{LB}len(embedding){RB}{RB}f', *embedding)


        def _bytes_to_embedding(data: bytes) -> list:
            """Unpack embedding from binary."""
            count = len(data) // 4
            return list(struct.unpack(f'{LB}{LB}count{RB}{RB}f', data))


        def get_embedding(text: str) -> list:
            """Get embedding vector for a text string."""
            truncated = text[:32000]
            embedding = openrouter.embed(truncated, model=MODEL)
            token_estimate = len(truncated) // 4
            cost_estimate = token_estimate * 0.13 / 1_000_000
            openrouter.log_cost_to_db(
                'embed', MODEL,
                {LB}'prompt_tokens': token_estimate, 'completion_tokens': 0{RB},
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
                f"[Embedder] {LB}olympiad_slug{RB}/{LB}grade{RB}/{LB}round_name{RB} "
                f"max_sim={LB}result['max_similarity']:.3f{RB} dup={LB}result['is_duplicate']{RB}"
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
                {LB}
                    'vec': embedding_literal,
                    'slug': olympiad_slug,
                    'grade': grade,
                    'round': round_name,
                    'cutoff': cutoff_date,
                {RB}
            ).fetchone()

            if row is None:
                return {LB}
                    'is_duplicate': False,
                    'max_similarity': 0.0,
                    'similar_problem_id': None,
                {RB}

            similarity = float(row[1])
            return {LB}
                'is_duplicate': similarity >= SIMILARITY_THRESHOLD,
                'max_similarity': round(similarity, 4),
                'similar_problem_id': row[0] if similarity >= SIMILARITY_THRESHOLD else None,
            {RB}


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
                {LB}
                    'slug': olympiad_slug,
                    'grade': grade,
                    'round': round_name,
                    'cutoff': cutoff_date.isoformat(),
                {RB}
            ).fetchall()

            max_sim = 0.0
            max_id = None

            for row in rows:
                stored_emb = _bytes_to_embedding(row[1])
                sim = _cosine_similarity(embedding, stored_emb)
                if sim > max_sim:
                    max_sim = sim
                    max_id = row[0]

            return {LB}
                'is_duplicate': max_sim >= SIMILARITY_THRESHOLD,
                'max_similarity': round(max_sim, 4),
                'similar_problem_id': max_id if max_sim >= SIMILARITY_THRESHOLD else None,
            {RB}


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
            import hashlib

            if use_pgvector:
                embedding_val = '[' + ','.join(str(x) for x in embedding) + ']'
                db.session.execute(
                    db.text("""
                        INSERT INTO problem_embeddings
                            (problem_id, statement_hash, olympiad_slug, grade, round, embedding)
                        VALUES (:pid, md5(:stmt), :slug, :grade, :round, :emb::vector)
                    """),
                    {LB}
                        'pid': problem_id,
                        'stmt': statement,
                        'slug': olympiad_slug,
                        'grade': grade,
                        'round': round_name,
                        'emb': embedding_val,
                    {RB}
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
                    {LB}
                        'pid': problem_id,
                        'hash': stmt_hash,
                        'slug': olympiad_slug,
                        'grade': grade,
                        'round': round_name,
                        'emb': emb_bytes,
                    {RB}
                )

            db.session.commit()
            logger.info(f'[Embedder] Saved embedding for problem {LB}problem_id{RB}')
    ''').lstrip('\n')

    path = os.path.join(OUT, "embedder.py")
    with open(path, 'w', encoding='utf-8') as f:
        f.write(code)
    print(f"  embedder.py: {len(code)} bytes")


def write_polisher():
    code = textwrap.dedent(f'''
        # -*- coding: utf-8 -*-
        """
        Polisher service: final formatting pass.
        Fixes LaTeX, improves wording, ensures consistency.
        CRITICAL: Does NOT change mathematical content.
        """
        import json
        import logging

        from services.openrouter_client import openrouter

        logger = logging.getLogger(__name__)

        MODEL = "openai/gpt-4o"
        TEMPERATURE = 0.2


        def polish_problem(problem: dict) -> dict:
            """
            Polish a problem: fix LaTeX, improve wording.

            Args:
                problem: dict with statement, solution, answer

            Returns: dict with polished statement, solution, answer, changes_made
            Fallback: returns original if model says no_change needed.
            """
            statement = problem.get('statement', '')
            solution = problem.get('solution', '')
            answer = problem.get('answer', '')

            prompt = _build_prompt(statement, solution, answer)

            result = openrouter.chat(
                model=MODEL,
                messages=[
                    {LB}"role": "system", "content": "\\u0422\\u044b \\u2014 \\u0440\\u0435\\u0434\\u0430\\u043a\\u0442\\u043e\\u0440-\\u043a\\u043e\\u0440\\u0440\\u0435\\u043a\\u0442\\u043e\\u0440 \\u043e\\u043b\\u0438\\u043c\\u043f\\u0438\\u0430\\u0434\\u043d\\u044b\\u0445 \\u0437\\u0430\\u0434\\u0430\\u0447. \\u0422\\u0432\\u043e\\u044f \\u0437\\u0430\\u0434\\u0430\\u0447\\u0430 \\u2014 \\u0444\\u0438\\u043d\\u0430\\u043b\\u044c\\u043d\\u0430\\u044f \\u043f\\u043e\\u043b\\u0438\\u0440\\u043e\\u0432\\u043a\\u0430 \\u0442\\u0435\\u043a\\u0441\\u0442\\u0430: \\u0438\\u0441\\u043f\\u0440\\u0430\\u0432\\u0438\\u0442\\u044c LaTeX, \\u0443\\u043b\\u0443\\u0447\\u0448\\u0438\\u0442\\u044c \\u0444\\u043e\\u0440\\u043c\\u0443\\u043b\\u0438\\u0440\\u043e\\u0432\\u043a\\u0438, \\u0443\\u0431\\u0440\\u0430\\u0442\\u044c \\u043b\\u0438\\u0448\\u043d\\u0435\\u0435. \\u041d\\u0415 \\u043c\\u0435\\u043d\\u044f\\u0442\\u044c \\u043c\\u0430\\u0442\\u0435\\u043c\\u0430\\u0442\\u0438\\u0447\\u0435\\u0441\\u043a\\u043e\\u0435 \\u0441\\u043e\\u0434\\u0435\\u0440\\u0436\\u0430\\u043d\\u0438\\u0435."{RB},
                    {LB}"role": "user", "content": prompt{RB}
                ],
                temperature=TEMPERATURE,
                max_tokens=4096,
            )

            content = result["content"]
            try:
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0]
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0]
                data = json.loads(content.strip())
            except json.JSONDecodeError:
                logger.error(f"[Polisher] JSON parse error: {LB}content[:200]{RB}")
                # Fallback: return original
                return {LB}
                    'statement': statement,
                    'solution': solution,
                    'answer': answer,
                    'changes_made': [],
                    '_error': 'JSON parse failed',
                    '_usage': result['usage'],
                    '_cost': result['cost_usd'],
                {RB}

            # Handle no_change response
            if data.get('status') == 'no_change':
                logger.info(f"[Polisher] No changes needed: {LB}data.get('reason', ''){RB}")
                return {LB}
                    'statement': statement,
                    'solution': solution,
                    'answer': answer,
                    'changes_made': [],
                    '_usage': result['usage'],
                    '_cost': result['cost_usd'],
                {RB}

            # Validate polished output has required fields
            for field in ['statement', 'solution', 'answer']:
                if not data.get(field):
                    data[field] = problem.get(field, '')

            data['_usage'] = result['usage']
            data['_cost'] = result['cost_usd']

            openrouter.log_cost_to_db('polish', MODEL, result['usage'], result['cost_usd'])
            changes = data.get('changes_made', [])
            logger.info(f"[Polisher] {LB}len(changes){RB} changes made, ${LB}result['cost_usd']:.4f{RB}")
            return data


        def _build_prompt(statement: str, solution: str, answer: str) -> str:
            """Build the polisher prompt."""
            return f"""\\u041e\\u0442\\u0440\\u0435\\u0434\\u0430\\u043a\\u0442\\u0438\\u0440\\u0443\\u0439 \\u0437\\u0430\\u0434\\u0430\\u0447\\u0443. \\u041d\\u0415 \\u041c\\u0415\\u041d\\u042f\\u0419 \\u043c\\u0430\\u0442\\u0435\\u043c\\u0430\\u0442\\u0438\\u043a\\u0443, \\u0442\\u043e\\u043b\\u044c\\u043a\\u043e \\u0443\\u043b\\u0443\\u0447\\u0448\\u0438 \\u043e\\u0444\\u043e\\u0440\\u043c\\u043b\\u0435\\u043d\\u0438\\u0435.

        \\u0423\\u0421\\u041b\\u041e\\u0412\\u0418\\u0415:
        {LB}statement{RB}

        \\u0420\\u0415\\u0428\\u0415\\u041d\\u0418\\u0415:
        {LB}solution{RB}

        \\u041e\\u0422\\u0412\\u0415\\u0422: {LB}answer{RB}

        \\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550
        \\u041a\\u0420\\u0418\\u0422\\u0418\\u0427\\u041d\\u042b\\u0415 \\u0417\\u0410\\u041f\\u0420\\u0415\\u0422\\u042b (\\u043d\\u0430\\u0440\\u0443\\u0448\\u0435\\u043d\\u0438\\u0435 = \\u0430\\u0432\\u0442\\u043e\\u043c\\u0430\\u0442\\u0438\\u0447\\u0435\\u0441\\u043a\\u0438\\u0439 reject):
        - \\u041d\\u0415 \\u043c\\u0435\\u043d\\u044f\\u0442\\u044c \\u0447\\u0438\\u0441\\u043b\\u0430, \\u043a\\u043e\\u044d\\u0444\\u0444\\u0438\\u0446\\u0438\\u0435\\u043d\\u0442\\u044b, \\u043a\\u043e\\u043d\\u0441\\u0442\\u0430\\u043d\\u0442\\u044b
        - \\u041d\\u0415 \\u043f\\u0435\\u0440\\u0435\\u0438\\u043c\\u0435\\u043d\\u043e\\u0432\\u044b\\u0432\\u0430\\u0442\\u044c \\u043f\\u0435\\u0440\\u0435\\u043c\\u0435\\u043d\\u043d\\u044b\\u0435 (a\\u2192x, n\\u2192k)
        - \\u041d\\u0415 \\u0434\\u043e\\u0431\\u0430\\u0432\\u043b\\u044f\\u0442\\u044c \\u0438 \\u043d\\u0435 \\u0443\\u0434\\u0430\\u043b\\u044f\\u0442\\u044c \\u0448\\u0430\\u0433\\u0438 \\u0440\\u0435\\u0448\\u0435\\u043d\\u0438\\u044f
        - \\u041d\\u0415 \\u0443\\u043f\\u0440\\u043e\\u0449\\u0430\\u0442\\u044c \\u0438 \\u043d\\u0435 \\u0440\\u0430\\u0441\\u043a\\u0440\\u044b\\u0432\\u0430\\u0442\\u044c \\u0444\\u043e\\u0440\\u043c\\u0443\\u043b\\u044b
        - \\u041d\\u0415 \\u043c\\u0435\\u043d\\u044f\\u0442\\u044c \\u043b\\u043e\\u0433\\u0438\\u043a\\u0443 \\u0434\\u043e\\u043a\\u0430\\u0437\\u0430\\u0442\\u0435\\u043b\\u044c\\u0441\\u0442\\u0432\\u0430
        - \\u041d\\u0415 \\u0438\\u0441\\u043f\\u0440\\u0430\\u0432\\u043b\\u044f\\u0442\\u044c "\\u043e\\u0448\\u0438\\u0431\\u043a\\u0438" \\u0432 \\u043c\\u0430\\u0442\\u0435\\u043c\\u0430\\u0442\\u0438\\u043a\\u0435 (\\u044d\\u0442\\u043e \\u043d\\u0435 \\u0442\\u0432\\u043e\\u044f \\u0437\\u0430\\u0434\\u0430\\u0447\\u0430)

        \\u041f\\u0440\\u0438 \\u041b\\u042e\\u0411\\u041e\\u041c \\u0441\\u043e\\u043c\\u043d\\u0435\\u043d\\u0438\\u0438 \\u2014 \\u0432\\u0435\\u0440\\u043d\\u0438 \\u0431\\u0435\\u0437 \\u0438\\u0437\\u043c\\u0435\\u043d\\u0435\\u043d\\u0438\\u0439:
        {LB}{LB}"status": "no_change", "reason": "\\u043e\\u043f\\u0438\\u0441\\u0430\\u043d\\u0438\\u0435 \\u0441\\u043e\\u043c\\u043d\\u0435\\u043d\\u0438\\u044f"{RB}{RB}

        \\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550\\u2550
        \\u041f\\u0420\\u0410\\u0412\\u0418\\u041b\\u0410 \\u0420\\u0415\\u0414\\u0410\\u041a\\u0422\\u0418\\u0420\\u041e\\u0412\\u0410\\u041d\\u0418\\u042f:

        1. LaTeX:
           - Inline