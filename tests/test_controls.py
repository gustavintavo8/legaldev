"""Tabla de mapeo y catálogo de controles (PP-09; RF-26; RNF-17).

Las guardas que corren hoy comprueban que los ficheros de datos del andamiaje se leen y
tienen la estructura prevista; la validación completa es PP-09.
"""

import pytest
import yaml

from app import controls


def _load(path):
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_mapping_file_has_expected_top_level_structure():
    data = _load(controls.MAPPING_PATH)
    assert set(data) == {"version", "fecha", "catalogos", "entradas"}
    assert isinstance(data["version"], str)
    assert set(data["catalogos"]) == {"iso27001", "ens"}
    controls.TablaMapeo.model_validate(data)


def test_catalog_identifiers_have_valid_format():
    data = _load(controls.CATALOG_PATH)
    catalogo = controls.Catalogo.model_validate(data)
    assert all(controls.ISO27001_ID.match(i) for i in catalogo.iso27001)
    assert all(controls.ENS_ID.match(i) for i in catalogo.ens)


@pytest.mark.skip(
    reason="TODO(PT3/PP-09): todo identificador del mapeo existe en el catálogo"
)
def test_pp09_every_mapping_identifier_exists_in_catalog():
    """validate_mapping(load_mapping(), load_catalog()) == []."""


@pytest.mark.skip(
    reason="TODO(PT3/PP-09): cada entrada tiene normativa, artículos o páginas y justificación"
)
def test_pp09_every_entry_has_source_key_and_justification():
    """articulos y paginas no pueden estar ambos vacíos; justificación no vacía."""


@pytest.mark.skip(
    reason="TODO(PT3/PP-09): no hay identificadores de obligación duplicados"
)
def test_pp09_no_duplicated_obligation_ids():
    """Ni ids repetidos ni dos entradas que reclamen el mismo (normativa, artículo)."""


@pytest.mark.skip(
    reason="TODO(PT3/PP-09): cada normativa del mapeo existe en app.corpus.REQUIRED_DOCS"
)
def test_pp09_mapping_normativas_are_corpus_files():
    """La clave normativa es el nombre de fichero del corpus (anexo del corpus)."""


@pytest.mark.skip(
    reason="TODO(PT3/RF-26): resolve_controls es determinista y no usa el LLM"
)
def test_rf26_resolve_controls_is_deterministic():
    """Misma obligación tipificada y misma tabla -> misma entrada, en cualquier orden."""


@pytest.mark.skip(
    reason="TODO(PT3/RF-26): entrada sin control técnico -> listas vacías y justificación fija"
)
def test_rf26_entry_without_technical_control_uses_fixed_justification():
    """iso27001 == ens == [] exige justificacion que empiece por SIN_CONTROL_TECNICO."""


@pytest.mark.skip(
    reason="TODO(PT3/CU-08): obligación tipificada sin entrada -> «sin mapeo» (flujo 3b)"
)
def test_cu08_typed_obligation_without_entry_is_unmapped():
    """resolve_controls devuelve None y la evidencia la lista en sin_mapeo."""


@pytest.mark.skip(
    reason="TODO(PT3/RNF-17): la tabla publicada lleva versión semver y fecha"
)
def test_rnf17_published_mapping_has_semver_and_date():
    """Aplicable desde la primera versión con entradas (hoy 0.0.0 y fecha nula)."""
