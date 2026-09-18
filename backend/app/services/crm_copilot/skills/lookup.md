# lookup

search_contacts / get_contact first. Include the HubSpot URL from the tool result.
get_contact and inspect_record already include notes, deals, tasks, filled fields, and recent calls — use that before answering "qué pasó", "notas", or follow-ups. Do not invent an empty history.
If last_contact_id is set and they ask for "the link" or "el enlace", get_contact that id.
search_deals / list_associated_deals only if they asked about a deal or after a contact is locked.
A new name or "otro deal" replaces focus — search again. Never start extract_sales_update for a question.
