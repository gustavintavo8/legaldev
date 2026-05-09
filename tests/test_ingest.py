from app.ingest import get_doc_type


def test_rgpd():
    assert get_doc_type("RGPD.pdf") == "normativa_europea"

def test_eu_ai_act():
    assert get_doc_type("EU AI Act.pdf") == "normativa_europea"

def test_nis2():
    assert get_doc_type("Directiva NIS2.pdf") == "normativa_europea"

def test_responsabilidad_ia():
    assert get_doc_type("Directiva de Responsabilidad por Productos con IA.pdf") == "normativa_europea"

def test_lopdgdd():
    assert get_doc_type("LOPDGDD.pdf") == "normativa_española"

def test_ens():
    assert get_doc_type("ENS Real Decreto 311-2022.pdf") == "normativa_española"

def test_lssi():
    assert get_doc_type("LSSI.pdf") == "normativa_española"

def test_propiedad_intelectual():
    assert get_doc_type("Ley de Propiedad Intelectual.pdf") == "normativa_española"

def test_codigo_etico():
    assert get_doc_type("Código Ético y Deontológico CCII.pdf") == "deontologia"

def test_aepd_cookies():
    assert get_doc_type("Guía sobre uso de cookies - AEPD.pdf") == "guia_aepd"

def test_aepd_anonimizacion():
    assert get_doc_type("Guía de Anonimización - AEPD.pdf") == "guia_aepd"

def test_aepd_adecuacion_ia():
    assert get_doc_type("Adecuación al RGPD de tratamientos que incorporan IA - AEPD.pdf") == "guia_aepd"

def test_unknown():
    assert get_doc_type("Documento desconocido.pdf") == "otro"
