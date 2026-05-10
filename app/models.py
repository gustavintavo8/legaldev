from pydantic import BaseModel, Field, model_validator
from typing import Self


class QuestionnaireInput(BaseModel):
    tipo_proyecto: str
    descripcion_breve: str = Field(max_length=500)
    tiene_usuarios_registrados: bool
    acceso_publico: bool

    tipos_datos_personales: list[str]
    usuarios_menores: bool
    usuarios_ue: bool
    transferencia_datos_terceros: bool

    usa_ia: bool
    tipo_ia: str | None = None
    usa_cookies: bool
    monetizacion: str | None = None
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
