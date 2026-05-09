from typing import Optional
from pydantic import BaseModel, Field


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
    tipo_ia: Optional[str] = None
    usa_cookies: bool
    monetizacion: Optional[str] = None
    contenido_digital: bool

    ccaa: str
    es_empresa: bool
    colegiado: Optional[bool] = None


class RAGResponse(BaseModel):
    respuesta_completa: str
    normativas_detectadas: list[str]
    chunks_utilizados: int
    disclaimer: str
