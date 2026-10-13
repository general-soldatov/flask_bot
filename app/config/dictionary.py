from .config import Reference, Lexicon
from typing import Dict, Literal, List

LEXICON = "/home/GeneralSoldatov/mysite/app/config/lexicon.yaml"
REFERENCE = "/home/GeneralSoldatov/mysite/app/config/reference.yaml"

reference = Reference.model_validate_yaml(REFERENCE)
lexicon = Lexicon.model_validate_yaml(LEXICON)

def library_button(subject: str, part: Literal['metodic', 'books'], type='link') -> List[Dict[str, str]]:
    return [{'label': lexicon.library[subject][part][key], type: url}
        for key, url in reference.library[subject][part].items()]

