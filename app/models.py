from datetime import datetime
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, Field, model_validator

from app.fragments import FragmentoRef


class TipoProyecto(StrEnum):
    APP_WEB = "app_web"
    API = "api"
    APP_MOVIL = "app_movil"
    SAAS = "saas"
    ECOMMERCE = "ecommerce"


class TipoDatoPersonal(StrEnum):
    NOMBRE = "nombre"
    EMAIL = "email"
    TELEFONO = "telefono"
    UBICACION = "ubicacion"
    SALUD = "salud"
    FINANCIEROS = "financieros"
    BIOMETRICOS = "biometricos"
    NINGUNO = "ninguno"


class TipoIA(StrEnum):
    GENERATIVA = "generativa"
    AGENTES = "agentes"
    RECOMENDACION = "recomendacion"
    CLASIFICACION = "clasificacion"
    VISION = "vision"
    OTRO = "otro"


class Monetizacion(StrEnum):
    SUSCRIPCION = "suscripcion"
    PUBLICIDAD = "publicidad"
    FREEMIUM = "freemium"
    PAGO_UNICO = "pago_unico"
    MARKETPLACE = "marketplace"
    NINGUNA = "ninguna"


# Valores deben coincidir carácter a carácter con los value= del <select id="ccaa">
# en legaldev-web/index.html. Si se añade una opción al frontend, añadirla aquí también.
class ComunidadAutonoma(StrEnum):
    ANDALUCIA = "Andalucía"
    ARAGON = "Aragón"
    ASTURIAS = "Asturias"
    BALEARES = "Baleares"
    CANARIAS = "Canarias"
    CANTABRIA = "Cantabria"
    CASTILLA_LM = "Castilla-La Mancha"
    CASTILLA_LEON = "Castilla y León"
    CATALUNA = "Cataluña"
    CEUTA = "Ceuta"
    EXTREMADURA = "Extremadura"
    GALICIA = "Galicia"
    LA_RIOJA = "La Rioja"
    MADRID = "Madrid"
    MELILLA = "Melilla"
    MURCIA = "Murcia"
    NAVARRA = "Navarra"
    PAIS_VASCO = "País Vasco"
    VALENCIA = "Valencia"


class QuestionnaireInput(BaseModel):
    tipo_proyecto: TipoProyecto
    descripcion_breve: str = Field(max_length=500)
    tiene_usuarios_registrados: bool
    acceso_publico: bool

    tipos_datos_personales: list[TipoDatoPersonal]
    usuarios_menores: bool
    usuarios_ue: bool
    transferencia_datos_terceros: bool

    usa_ia: bool
    tipo_ia: TipoIA | None = None
    usa_cookies: bool
    monetizacion: Monetizacion | None = None
    contenido_digital: bool

    ccaa: ComunidadAutonoma
    es_empresa: bool
    colegiado: bool | None = None

    @model_validator(mode="after")
    def tipo_ia_required_when_usa_ia(self) -> Self:
        if self.usa_ia and not self.tipo_ia:
            raise ValueError("tipo_ia es obligatorio cuando usa_ia es True")
        return self


class CitationStats(BaseModel):
    total: int
    verificadas: int
    no_verificadas: list[str]


class SaneadoStats(BaseModel):
    """Lo que el saneado de la salida (``app/sanitize.py``, RNF-20) ha retirado o neutralizado
    en el texto del modelo, por tipo. Solo recuentos: nunca el contenido retirado."""

    bloques_herramienta: int = Field(
        default=0, description="Bloques que imitan llamadas a herramientas."
    )
    imagenes: int = Field(default=0, description="Imágenes Markdown (todas).")
    enlaces: int = Field(
        default=0,
        description=(
            "Enlaces Markdown, autoenlaces y definiciones de referencia a destinos que no "
            "son los dominios oficiales del corpus (queda el texto del enlace)."
        ),
    )
    html: int = Field(default=0, description="Etiquetas, bloques y comentarios HTML.")
    urls: int = Field(
        default=0,
        description=(
            "URL sueltas que no son de un dominio oficial ni aparecen en los fragmentos: "
            "se muestran como código, sin enlace."
        ),
    )
    caracteres_control: int = Field(
        default=0, description="Caracteres de control y secuencias de escape ANSI."
    )
    caracteres_invisibles: int = Field(
        default=0,
        description=(
            "Caracteres de ancho cero, de dirección bidi, etiquetas Unicode y selectores "
            "de variación."
        ),
    )
    bloques_codigo_sin_cerrar: int = Field(
        default=0, description="Bloques de código sin cerrar, que se han cerrado."
    )

    def total(self) -> int:
        return sum(self.model_dump().values())


class GeneradoPorIA(BaseModel):
    """Marcado legible por máquina del contenido generado por IA (Reglamento de IA, art.
    50.2; hallazgo C-05 de la revisión jurídica).

    Lo generado es el texto del informe que redacta el modelo. El aviso de no asesoramiento y
    las secciones «Cobertura del análisis», «Saneado de la salida» y «Verificación de citas»
    las añade el código.
    """

    modelo: str = Field(
        description="Modelo que redactó el informe (el de respaldo si lo hizo él)."
    )
    proveedor: str = Field(description="Proveedor del modelo.")
    fecha: datetime = Field(
        description="Momento de la generación, en UTC (ISO 8601). Una respuesta de la "
        "caché conserva la fecha en que se generó."
    )


class RAGResponse(BaseModel):
    respuesta_completa: str
    normativas_detectadas: list[str]
    chunks_utilizados: int
    disclaimer: str
    corpus_version: str = "unknown"
    llm_model: str = "unknown"
    citas: CitationStats = Field(
        default_factory=lambda: CitationStats(total=0, verificadas=0, no_verificadas=[])
    )
    # RNF-20: qué se ha retirado del texto del modelo antes de entregarlo.
    saneado: SaneadoStats = Field(default_factory=SaneadoStats)
    # C-05 (Reglamento de IA, art. 50.2): el informe lo ha generado un modelo de IA.
    generado_por_ia: GeneradoPorIA | None = None


class PipelineResult(BaseModel):
    """Resultado interno de un análisis: la respuesta REST y los fragmentos del contexto.

    La API REST devuelve solo ``response`` (su forma pública no cambia); ``analizar_proyecto``
    publica además los fragmentos, sin texto, en el orden en que los recibe el modelo. Es lo
    que guarda la caché común (``service.analyze``).
    """

    response: RAGResponse
    fragmentos: list[FragmentoRef]
    # Detectadas a las que el informe no dedica sección (citations.normativas_sin_desarrollar).
    normativas_sin_desarrollar: list[str] = Field(default_factory=list)


class FeedbackInput(BaseModel):
    # X-Request-ID es hex de 8 chars generado por el servidor; se admite también formato UUID.
    request_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    rating: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=2000)
