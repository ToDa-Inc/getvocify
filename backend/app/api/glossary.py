from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional, Dict, Any
import logging
import uuid
from app.deps import get_supabase, get_user_id
from app.services.glossary import GlossaryService
from app.services.glossary_templates import TemplateService
from app.services.glossary_ai import GlossaryAIService
from pydantic import BaseModel, Field
from supabase import Client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/glossary", tags=["glossary"])

@router.get("/templates", response_model=List[Dict[str, Any]])
async def list_templates():
    return TemplateService.get_all_templates()

@router.post("/import/{template_id}", response_model=List[dict])
async def import_template(
    template_id: str,
    user_id: str = Depends(get_user_id),
    supabase: Client = Depends(get_supabase)
):
    template = TemplateService.get_template(template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
        
    service = GlossaryService(supabase)
    current_glossary = await service.get_user_glossary(user_id)
    
    # Merge items, avoiding duplicates by target_word
    existing_words = {i.get("target_word") for i in current_glossary}
    new_items = []
    for item in template["items"]:
        if item["target_word"] not in existing_words:
            # Add a unique ID to each imported item
            item_with_id = item.copy()
            item_with_id["id"] = str(uuid.uuid4())
            new_items.append(item_with_id)
            
    if not new_items:
        return current_glossary
        
    updated_glossary = current_glossary + new_items
    return await service.update_glossary(user_id, updated_glossary)

class GlossaryItem(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    target_word: str
    phonetic_hints: List[str] = Field(default_factory=list)
    boost_factor: int = 5
    category: str = "General"

class GlossaryUpdate(BaseModel):
    target_word: Optional[str] = None
    phonetic_hints: Optional[List[str]] = None
    boost_factor: Optional[int] = None
    category: Optional[str] = None

@router.get("", response_model=List[dict])
async def get_glossary(
    user_id: str = Depends(get_user_id),
    supabase: Client = Depends(get_supabase)
):
    service = GlossaryService(supabase)
    return await service.get_user_glossary(user_id)

@router.post("", response_model=dict)
async def add_glossary_item(
    item: GlossaryItem,
    user_id: str = Depends(get_user_id),
    supabase: Client = Depends(get_supabase)
):
    service = GlossaryService(supabase)
    current_glossary = await service.get_user_glossary(user_id)
    
    # Check if word already exists
    if any(i.get("target_word") == item.target_word for i in current_glossary):
        raise HTTPException(status_code=400, detail=f"Word '{item.target_word}' already exists in glossary")
        
    # SMART FEATURE: Auto-generate phonetic hints if none provided
    item_data = item.model_dump()
    if not item_data.get("phonetic_hints"):
        ai_service = GlossaryAIService()
        hints = await ai_service.generate_phonetic_hints(item.target_word, item.category)
        if hints:
            item_data["phonetic_hints"] = hints
            logger.info(f"AI generated {len(hints)} hints for '{item.target_word}': {hints}")

    current_glossary.append(item_data)
    updated = await service.update_glossary(user_id, current_glossary)
    
    # Find and return the newly added item
    return next(i for i in updated if i.get("target_word") == item.target_word)

@router.patch("/{item_id}", response_model=dict)
async def update_glossary_item(
    item_id: str,
    update: GlossaryUpdate,
    user_id: str = Depends(get_user_id),
    supabase: Client = Depends(get_supabase)
):
    service = GlossaryService(supabase)
    current_glossary = await service.get_user_glossary(user_id)
    
    item_index = -1
    for i, item in enumerate(current_glossary):
        if item.get("id") == item_id:
            item_index = i
            break
            
    if item_index == -1:
        raise HTTPException(status_code=404, detail="Item not found")
    
    # Update fields
    data = update.model_dump(exclude_none=True)
    current_glossary[item_index].update(data)
    
    updated = await service.update_glossary(user_id, current_glossary)
    return updated[item_index]

@router.delete("/{item_id}")
async def delete_glossary_item(
    item_id: str,
    user_id: str = Depends(get_user_id),
    supabase: Client = Depends(get_supabase)
):
    service = GlossaryService(supabase)
    current_glossary = await service.get_user_glossary(user_id)
    
    new_glossary = [i for i in current_glossary if i.get("id") != item_id]
    
    if len(new_glossary) == len(current_glossary):
        raise HTTPException(status_code=404, detail="Item not found")
        
    await service.update_glossary(user_id, new_glossary)
    return {"success": True}

@router.get("/suggest/{word}")
async def suggest_hints(
    word: str,
    category: str = "General"
):
    ai_service = GlossaryAIService()
    hints = await ai_service.generate_phonetic_hints(word, category)
    return {"word": word, "hints": hints}
