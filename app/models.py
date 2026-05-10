from enum import StrEnum
from typing import Self

from pydantic import BaseModel, Field, model_validator


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

    ccaa: str
    es_empresa: bool
    colegiado: bool | None = None

    @model_validator(mode="after")
    def tipo_ia_required_when_usa_ia(self) -> Self:
        if self.usa_ia and not self.tipo_ia:
            raise ValueError("tipo_ia es obligatorio cuando usa_ia es True")
        return self


class RAGResponse(BaseModel):
    respuesta_completa: str
    normativas_detectadas: list[str]
    chunks_utilizados: int
    disclaimer: str
