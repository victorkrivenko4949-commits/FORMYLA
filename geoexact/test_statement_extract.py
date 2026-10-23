"""Supported-clause extraction and coordinate audit; no LLM calls."""
from geoexact.core.statement_extract import extract, audit_statement

TEXT = ("В треугольнике ABC биссектриса BE и медиана AD перпендикулярны "
        "и имеют одинаковую длину, равную 12. Найдите стороны треугольника ABC.")
P = dict(A=(-6.,9.),B=(0.,0.),C=(12.,18.),D=(6.,9.),E=(0.,12.))


def test_original_statement():
    report = audit_statement(TEXT,P)
    assert report['ok'] and len(report['requirements']) == 7
    assert report['goals'] == ['Найдите стороны треугольника ABC']


def test_equivalent_separate_clauses():
    text = 'Дан треугольник ABC. AD — медиана. BE — биссектриса. AD ⊥ BE. AD = BE = 12.'
    assert audit_statement(text,P)['ok']
    assert len(extract(text).requirements) == 7


def test_renaming_numbers_and_role_order():
    for names in ('ABCDE','PQRST','XYZUV'):
        table = str.maketrans(dict(zip('ABCDE',names)))
        for length in (6,12,24):
            for swapped in (False,True):
                text = TEXT.replace('12',str(length))
                if swapped:
                    text = text.replace('биссектриса BE и медиана AD','медиана AD и биссектриса BE')
                text = text.translate(table)
                points = {n.translate(table):(x*length/12,y*length/12) for n,(x,y) in P.items()}
                assert audit_statement(text,points)['ok']


def test_unknown_clause_blocks_verification():
    for extra in (' AB + BC = 18.', ' BC касается окружности.', ' угол A острый.'):
        report = audit_statement(TEXT+extra,P)
        assert not report['ok'] and report['status'] == 'incomplete'
        assert report['unparsed']


def test_condition_inside_question_is_not_ignored():
    report = audit_statement('Дан треугольник ABC. Найдите AB, если AC = 1.',P)
    assert not report['ok'] and report['unparsed']


def test_negation_not_parsed_as_positive():
    text = TEXT.replace('перпендикулярны','не перпендикулярны')
    report = audit_statement(text,P)
    assert not report['ok'] and report['status'] == 'incomplete'


def test_wrong_or_missing_coordinates_fail():
    wrong = dict(P);wrong['D'] = (3.,1.)
    assert audit_statement(TEXT,wrong)['status'] == 'violated'
    missing = dict(P);del missing['E']
    assert not audit_statement(TEXT,missing)['ok']


def test_decimal_lengths():
    for value in ('12.5','12,5'):
        points = {n:(x*12.5/12,y*12.5/12) for n,(x,y) in P.items()}
        assert audit_statement(TEXT.replace('12',value),points)['ok']


def test_ambiguous_triangle_and_empty_input():
    assert not audit_statement('Дан треугольник ABC. Дан треугольник ABF. BE — биссектриса.',P)['ok']
    assert not audit_statement('',P)['ok']


def test_other_relation_types():
    points = dict(A=(0.,0.),B=(2.,0.),C=(0.,1.),D=(2.,1.),M=(1.,0.))
    assert audit_statement('M — середина AB. AB ∥ CD. AB = CD.',points)['ok']
