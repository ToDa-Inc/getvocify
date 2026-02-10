from typing import List, Dict, Any

GLOSSARY_TEMPLATES = {
    "spain-tech-sales": {
        "id": "spain-tech-sales",
        "name": "Spain Tech Sales (SaaS)",
        "description": "Common Spanglish terms, phonetic fixes for Spanish accents, and sales lingo used in Spain.",
        "items": [
            {
                "target_word": "Edenred",
                "phonetic_hints": ["En red", "Enred", "Eden red", "Edén red"],
                "boost_factor": 8,
                "category": "Company"
            },
            {
                "target_word": "Cobee",
                "phonetic_hints": ["Covid", "Cobi", "Kobi", "Cobe"],
                "boost_factor": 8,
                "category": "Company"
            },
            {
                "target_word": "Fee mensual",
                "phonetic_hints": ["Femen sual", "Fin mensual", "Fimen sual"],
                "boost_factor": 6,
                "category": "Slang"
            },
            {
                "target_word": "50k",
                "phonetic_hints": ["50 kas", "50 cash", "Cincuenta kas", "50 mil"],
                "boost_factor": 7,
                "category": "Slang"
            },
            {
                "target_word": "FTES",
                "phonetic_hints": ["FPS", "FTS", "FT is", "Efetes", "Efete ese", "Efectivos"],
                "boost_factor": 8,
                "category": "Product"
            },
            {
                "target_word": "El budget",
                "phonetic_hints": ["El bachet", "El bayet", "El buche"],
                "boost_factor": 6,
                "category": "Slang"
            },
            {
                "target_word": "Decision Maker",
                "phonetic_hints": ["Decisión meiquer", "El que decide"],
                "boost_factor": 6,
                "category": "Slang"
            },
            {
                "target_word": "Follow-up",
                "phonetic_hints": ["Fólow up", "Folouap", "Seguimiento"],
                "boost_factor": 6,
                "category": "Slang"
            },
            {
                "target_word": "Forecast",
                "phonetic_hints": ["Forcas", "Fórcast"],
                "boost_factor": 5,
                "category": "Slang"
            }
        ]
    }
}

class TemplateService:
    @staticmethod
    def get_all_templates() -> List[Dict[str, Any]]:
        return [
            {
                "id": tid,
                "name": t["name"],
                "description": t["description"],
                "item_count": len(t["items"])
            }
            for tid, t in GLOSSARY_TEMPLATES.items()
        ]

    @staticmethod
    def get_template(template_id: str) -> Dict[str, Any]:
        return GLOSSARY_TEMPLATES.get(template_id)
