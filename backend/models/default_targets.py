from pydantic import BaseModel


class DefaultTargetItem(BaseModel):
    name: str
    namespace: str


class DefaultTargetsResponse(BaseModel):
    isvc: DefaultTargetItem
    llmisvc: DefaultTargetItem
    configmap_updated: bool = True


class DefaultTargetsPatch(BaseModel):
    isvc: DefaultTargetItem | None = None
    llmisvc: DefaultTargetItem | None = None
