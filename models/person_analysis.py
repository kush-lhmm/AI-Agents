from typing import List, Optional, Literal
from pydantic import BaseModel, Field

class BBox(BaseModel):
    x0: float = Field(ge=0, le=1)
    y0: float = Field(ge=0, le=1)
    x1: float = Field(ge=0, le=1)
    y1: float = Field(ge=0, le=1)

class Hair(BaseModel):
    style: Literal["straight","wavy","curly","coily","braided","bun","ponytail","buzz","bald","covered","unclear"]
    length: Literal["very_short","short","medium","long","very_long","unclear"]
    color: Literal["black","brown","blonde","red","gray","white","dyed_color","mixed","unclear"]

class Eyes(BaseModel):
    color: Literal["brown","black","blue","green","hazel","gray","unclear"]
    eyewear: Literal["none","glasses","sunglasses","goggles","unclear"]

class FacialHair(BaseModel):
    presence: Literal["none","mustache","beard","goatee","stubble","unclear"]

class Expression(BaseModel):
    mood: Literal["neutral","happy","surprised","angry","sad","focused","unclear"]
    mouth_open: bool
    smiling: bool

class Pose(BaseModel):
    view: Literal["frontal","three_quarter","profile","back","unclear"]
    head_tilt: Literal["left","right","up","down","none","unclear"]

class FaceAttributes(BaseModel):
    bbox: BBox
    occluded: bool
    age_bracket: Literal["child","teen","adult","senior","unclear"]
    hair: Hair
    eyes: Eyes
    facial_hair: FacialHair
    headwear: Literal["none","cap","hat","helmet","scarf","hood","religious_covering","unclear"]
    expression: Expression
    pose: Pose
    accessories: List[Literal[
        "earrings","necklace","mask","earbuds","headphones","tie","bowtie","watch","bracelet","bindi","unclear"
    ]]

class PeopleSummary(BaseModel):
    has_person: bool
    num_faces: int
    faces: List[FaceAttributes]

class Environment(BaseModel):
    setting: Literal["indoor","outdoor","vehicle","studio","stadium","nature","street","home","office","shop","unclear"]
    dominant_colors: List[Literal["black","white","gray","red","orange","yellow","green","blue","purple","brown","pink"]]

class Safety(BaseModel):
    nsfw: bool
    minors_possible: bool
    sensitive_context: bool 

class PersonImageAnalysis(BaseModel):
    caption: str
    people: PeopleSummary
    environment: Environment
    ocr_text: str
    suggested_actions: List[str]
    safety: Safety
