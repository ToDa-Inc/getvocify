import { useState, useEffect, useCallback } from "react";
import { Plus, Trash2, Loader2, BookOpen, Sparkles, Languages, Library, Wand2, Upload, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { glossaryApi, GlossaryItem, GlossaryTemplate, BulkAddItem } from "@/lib/api/glossary";
import { parseBulkInput, type ParsedBulkItem } from "@/lib/glossary/parseBulkInput";

export const UserGlossary = () => {
  const [items, setItems] = useState<GlossaryItem[]>([]);
  const [templates, setTemplates] = useState<GlossaryTemplate[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isAdding, setIsAdding] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [isImporting, setIsImporting] = useState(false);
  const [showTemplates, setShowTemplates] = useState(false);
  const [newWord, setNewWord] = useState("");
  const [newHints, setNewHints] = useState("");
  const [newCategory, setNewCategory] = useState("Company");
  const [showBulkAdd, setShowBulkAdd] = useState(false);
  const [bulkInput, setBulkInput] = useState("");
  const [bulkPreview, setBulkPreview] = useState<(ParsedBulkItem & { id: string; include: boolean })[]>([]);
  const [bulkCategory, setBulkCategory] = useState("Company");
  const [isBulkSuggesting, setIsBulkSuggesting] = useState(false);
  const [isBulkAdding, setIsBulkAdding] = useState(false);
  const [isDragOver, setIsDragOver] = useState(false);

  const existingWords = useCallback(() => new Set(items.map((i) => i.target_word)), [items]);

  const refreshBulkPreview = useCallback(() => {
    const parsed = parseBulkInput(bulkInput, bulkCategory);
    const existing = existingWords();
    setBulkPreview(
      parsed.map((p, idx) => ({
        ...p,
        id: `bulk-${idx}-${p.word}`,
        include: !existing.has(p.word),
      })),
    );
  }, [bulkInput, bulkCategory, existingWords]);

  useEffect(() => {
    if (bulkInput.trim()) refreshBulkPreview();
    else setBulkPreview([]);
  }, [bulkInput, bulkCategory, refreshBulkPreview]);

  const handleBulkFile = useCallback(
    (file: File) => {
      if (!file || !/\.(csv|txt)$/i.test(file.name)) {
        toast.error("Please upload a .csv or .txt file");
        return;
      }
      const reader = new FileReader();
      reader.onload = () => {
        const text = String(reader.result ?? "");
        setBulkInput((prev) => (prev ? `${prev}\n${text}` : text));
      };
      reader.readAsText(file);
    },
    [],
  );

  const handleBulkSuggest = useCallback(async () => {
    const toSuggest = bulkPreview.filter((p) => p.include && p.hints.length === 0).map((p) => p.word);
    if (toSuggest.length === 0) {
      toast.info("All selected words already have hints");
      return;
    }
    try {
      setIsBulkSuggesting(true);
      const result = await glossaryApi.bulkSuggest(toSuggest, bulkCategory);
      setBulkPreview((prev) =>
        prev.map((p) => ({
          ...p,
          hints: result[p.word] ?? p.hints,
        })),
      );
      toast.success(`Generated hints for ${Object.keys(result).length} words`);
    } catch {
      toast.error("Failed to generate sound-alikes");
    } finally {
      setIsBulkSuggesting(false);
    }
  }, [bulkPreview, bulkCategory]);

  const handleBulkAdd = useCallback(async () => {
    const toAdd = bulkPreview
      .filter((p) => p.include)
      .map((p) => ({
        target_word: p.word,
        phonetic_hints: p.hints,
        category: p.category,
      } satisfies BulkAddItem));
    if (toAdd.length === 0) {
      toast.error("Select at least one word to add");
      return;
    }
    try {
      setIsBulkAdding(true);
      const { added, skipped } = await glossaryApi.bulkAdd(toAdd);
      toast.success(`Added ${added} words${skipped > 0 ? `. ${skipped} skipped (already in glossary)` : ""}`);
      setBulkInput("");
      setBulkPreview([]);
      setShowBulkAdd(false);
      fetchGlossary();
    } catch {
      toast.error("Failed to add words");
    } finally {
      setIsBulkAdding(false);
    }
  }, [bulkPreview]);

  const setPreviewHints = useCallback((id: string, hints: string[]) => {
    setBulkPreview((prev) => prev.map((p) => (p.id === id ? { ...p, hints } : p)));
  }, []);

  const setPreviewInclude = useCallback((id: string, include: boolean) => {
    setBulkPreview((prev) => prev.map((p) => (p.id === id ? { ...p, include } : p)));
  }, []);

  const removePreviewItem = useCallback((id: string) => {
    setBulkPreview((prev) => prev.filter((p) => p.id !== id));
  }, []);

  useEffect(() => {
    Promise.all([fetchGlossary(), fetchTemplates()]);
  }, []);

  const fetchGlossary = async () => {
    try {
      const data = await glossaryApi.getGlossary();
      setItems(data);
    } catch (error) {
      console.error("Failed to fetch glossary", error);
    }
  };

  const fetchTemplates = async () => {
    try {
      const data = await glossaryApi.getTemplates();
      setTemplates(data);
    } catch (error) {
      console.error("Failed to fetch templates", error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSuggest = async () => {
    if (!newWord.trim()) return;
    try {
      setIsGenerating(true);
      const data = await glossaryApi.suggestHints(newWord, newCategory);
      setNewHints(data.hints.join(", "));
      toast.success("AI generated phonetic hints!");
    } catch (error) {
      toast.error("Failed to generate hints");
    } finally {
      setIsGenerating(false);
    }
  };

  const handleImport = async (templateId: string) => {
    try {
      setIsImporting(true);
      await glossaryApi.importTemplate(templateId);
      toast.success("Template imported successfully!");
      setShowTemplates(false);
      fetchGlossary();
    } catch (error) {
      toast.error("Failed to import template");
    } finally {
      setIsImporting(false);
    }
  };

  const handleAdd = async () => {
    if (!newWord.trim()) return;
    
    try {
      setIsGenerating(true);
      // If hints are empty, they will be auto-generated by the backend
      const hints = newHints.split(",").map(h => h.trim()).filter(h => h);
      await glossaryApi.addItem({
        target_word: newWord,
        phonetic_hints: hints,
        category: newCategory,
        boost_factor: 5
      });
      
      toast.success(`Added "${newWord}" to your glossary`);
      setNewWord("");
      setNewHints("");
      setIsAdding(false);
      fetchGlossary();
    } catch (error) {
      toast.error("Failed to add word");
    } finally {
      setIsGenerating(false);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await glossaryApi.deleteItem(id);
      toast.success("Removed from glossary");
      fetchGlossary();
    } catch (error) {
      toast.error("Failed to delete word");
    }
  };

  if (isLoading) {
    return (
      <div className="flex justify-center p-8">
        <Loader2 className="h-6 w-6 animate-spin text-beige" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-beige/10 flex items-center justify-center">
            <BookOpen className="h-5 w-5 text-beige" />
          </div>
          <div>
            <h3 className="font-bold text-foreground">Custom Vocabulary</h3>
            <p className="text-xs text-muted-foreground">Train AI to recognize your specific terms.</p>
          </div>
        </div>
        <div className="flex gap-2">
          <Button 
            variant="ghost" 
            size="sm" 
            onClick={() => setShowTemplates(!showTemplates)}
            className={`rounded-full ${showTemplates ? 'bg-beige/10 text-beige' : 'text-muted-foreground'}`}
          >
            <Library className="h-4 w-4 mr-2" />
            Packs
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setShowBulkAdd(!showBulkAdd)}
            className={`rounded-full border-beige/30 text-beige hover:bg-beige/5 ${showBulkAdd ? "bg-beige/10" : ""}`}
          >
            {showBulkAdd ? "Cancel" : <><Upload className="h-4 w-4 mr-2" /> Bulk add</>}
          </Button>
          <Button 
            variant="outline" 
            size="sm" 
            onClick={() => setIsAdding(!isAdding)}
            className="rounded-full border-beige/30 text-beige hover:bg-beige/5"
          >
            {isAdding ? "Cancel" : <><Plus className="h-4 w-4 mr-2" /> Add</>}
          </Button>
        </div>
      </div>

      {showBulkAdd && (
        <div className="p-6 rounded-2xl bg-secondary/5 border border-beige/20 space-y-6 animate-in fade-in slide-in-from-top-2">
          <div>
            <h4 className={`${THEME_TOKENS.typography.capsLabel} mb-2`}>Bulk import</h4>
            <p className="text-xs text-muted-foreground mb-4">
              Paste words (one per line or comma-separated), or drop a CSV/TXT file. CSV can include: word,category,hints
            </p>
            <div
              className={`relative rounded-2xl border-2 border-dashed transition-colors ${
                isDragOver ? "border-beige bg-beige/5" : "border-beige/20 hover:border-beige/40"
              }`}
              onDragOver={(e) => { e.preventDefault(); setIsDragOver(true); }}
              onDragLeave={() => setIsDragOver(false)}
              onDrop={(e) => {
                e.preventDefault();
                setIsDragOver(false);
                const f = e.dataTransfer.files[0];
                if (f) handleBulkFile(f);
              }}
            >
              <textarea
                value={bulkInput}
                onChange={(e) => setBulkInput(e.target.value)}
                placeholder={'Edenred\nFTES\nCobee, 50k\n\nOr CSV: word,category,hints'}
                className="w-full min-h-[140px] p-4 pr-12 rounded-2xl bg-transparent text-sm resize-y focus:outline-none focus:ring-0 placeholder:text-muted-foreground/50"
              />
              <label className="absolute top-3 right-3 w-8 h-8 flex items-center justify-center rounded-lg hover:bg-beige/10 cursor-pointer text-muted-foreground/60 hover:text-beige transition-colors">
                <input
                  type="file"
                  accept=".csv,.txt"
                  className="sr-only"
                  onChange={(e) => { const f = e.target.files?.[0]; if (f) handleBulkFile(f); e.target.value = ""; }}
                />
                <Upload className="h-5 w-5" />
              </label>
            </div>
            <p className="text-[10px] text-muted-foreground mt-2">Supported: .csv, .txt</p>
          </div>

          {bulkPreview.length > 0 && (
            <>
              <div className="flex flex-wrap items-center gap-3">
                <span className="text-xs font-bold text-muted-foreground">
                  {bulkPreview.filter((p) => p.include).length} to add
                  {bulkPreview.some((p) => !p.include) && ` · ${bulkPreview.filter((p) => !p.include).length} already in glossary`}
                </span>
                <span className="text-xs text-muted-foreground">Category:</span>
                <select
                  className="h-8 px-3 rounded-lg border border-input bg-white text-xs font-medium"
                  value={bulkCategory}
                  onChange={(e) => setBulkCategory(e.target.value)}
                >
                  <option value="Company">Company</option>
                  <option value="Competitor">Competitor</option>
                  <option value="Product">Product</option>
                  <option value="Technical">Technical</option>
                  <option value="Slang">Slang/Lingo</option>
                  <option value="General">General</option>
                </select>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={isBulkSuggesting || !bulkPreview.some((p) => p.include && p.hints.length === 0)}
                  onClick={handleBulkSuggest}
                  className="rounded-full text-xs h-8"
                >
                  {isBulkSuggesting ? <Loader2 className="h-3 w-3 animate-spin" /> : <Wand2 className="h-3 w-3 mr-1" />}
                  Generate missing sound-alikes
                </Button>
              </div>

              <div className="max-h-[280px] overflow-auto rounded-xl border border-border/20">
                <table className="w-full text-sm">
                  <thead className="sticky top-0 bg-secondary/95 border-b border-border/20">
                    <tr className="text-left">
                      <th className="w-10 p-2"></th>
                      <th className="p-2 font-medium">Word</th>
                      <th className="p-2 font-medium">Category</th>
                      <th className="p-2 font-medium flex-1">Sound-alikes</th>
                      <th className="w-10 p-2"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {bulkPreview.map((row) => (
                      <tr
                        key={row.id}
                        className={`border-b border-border/10 last:border-0 ${!row.include ? "opacity-50 bg-muted/20" : ""}`}
                      >
                        <td className="p-2">
                          <input
                            type="checkbox"
                            checked={row.include}
                            onChange={(e) => setPreviewInclude(row.id, e.target.checked)}
                            className="rounded border-input"
                          />
                        </td>
                        <td className="p-2 font-medium">{row.word}</td>
                        <td className="p-2">
                          <select
                            className="h-7 px-2 rounded border border-input bg-white text-xs w-28"
                            value={row.category}
                            onChange={(e) =>
                              setBulkPreview((prev) =>
                                prev.map((p) => (p.id === row.id ? { ...p, category: e.target.value } : p))
                              )
                            }
                          >
                            <option value="Company">Company</option>
                            <option value="Competitor">Competitor</option>
                            <option value="Product">Product</option>
                            <option value="Technical">Technical</option>
                            <option value="Slang">Slang</option>
                            <option value="General">General</option>
                          </select>
                        </td>
                        <td className="p-2">
                          <Input
                            value={row.hints.join(", ")}
                            onChange={(e) =>
                              setPreviewHints(
                                row.id,
                                e.target.value.split(/[,|;]/).map((h) => h.trim()).filter(Boolean),
                              )
                            }
                            placeholder="En red, Enred"
                            className="h-7 text-xs rounded-lg"
                          />
                        </td>
                        <td className="p-2">
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-7 w-7 text-muted-foreground hover:text-destructive"
                            onClick={() => removePreviewItem(row.id)}
                          >
                            <X className="h-3.5 w-3.5" />
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <Button
                variant="hero"
                disabled={isBulkAdding || !bulkPreview.some((p) => p.include)}
                onClick={handleBulkAdd}
                className="w-full rounded-full bg-beige text-cream font-bold"
              >
                {isBulkAdding ? (
                  <><Loader2 className="h-4 w-4 animate-spin mr-2" /> Adding...</>
                ) : (
                  <>Add {bulkPreview.filter((p) => p.include).length} to glossary</>
                )}
              </Button>
            </>
          )}
        </div>
      )}

      {showTemplates && (
        <div className="p-6 rounded-2xl bg-beige/5 border border-beige/20 space-y-4 animate-in fade-in zoom-in-95">
          <div className="flex items-center justify-between mb-2">
            <h4 className="text-xs font-black uppercase tracking-widest text-beige">Available Starter Packs</h4>
            <span className="text-[10px] text-muted-foreground italic">Instant setup for your industry</span>
          </div>
          <div className="grid gap-3">
            {templates.map(t => (
              <div key={t.id} className="flex items-center justify-between p-4 bg-white rounded-xl border border-beige/10 shadow-sm hover:border-beige/30 transition-all group">
                <div className="flex-1">
                  <h5 className="font-bold text-sm text-foreground">{t.name}</h5>
                  <p className="text-[10px] text-muted-foreground line-clamp-1">{t.description}</p>
                </div>
                <Button 
                  size="sm" 
                  disabled={isImporting}
                  onClick={() => handleImport(t.id)}
                  className="rounded-full bg-beige hover:bg-beige-dark text-white text-[10px] font-black uppercase px-4"
                >
                  {isImporting ? <Loader2 className="h-3 w-3 animate-spin" /> : "Import Pack"}
                </Button>
              </div>
            ))}
          </div>
        </div>
      )}

      {isAdding && (
        <div className="p-6 rounded-2xl bg-secondary/5 border border-beige/20 space-y-4 animate-in fade-in slide-in-from-top-2">
          <div className="grid sm:grid-cols-2 gap-4">
            <div className="space-y-2">
              <label className={THEME_TOKENS.typography.capsLabel}>Word / Name</label>
              <div className="relative">
                <Input 
                  placeholder="e.g. Edenred" 
                  value={newWord}
                  onChange={(e) => setNewWord(e.target.value)}
                  className="rounded-full bg-white font-bold pr-10"
                />
                <button 
                  onClick={handleSuggest}
                  disabled={isGenerating || !newWord}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-beige hover:text-beige-dark disabled:opacity-30 transition-colors"
                  title="Generate AI hints"
                >
                  {isGenerating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Wand2 className="h-4 w-4" />}
                </button>
              </div>
            </div>
            <div className="space-y-2">
              <label className={THEME_TOKENS.typography.capsLabel}>Category</label>
              <select 
                className="w-full h-10 px-4 rounded-full border border-input bg-white text-sm font-bold"
                value={newCategory}
                onChange={(e) => setNewCategory(e.target.value)}
              >
                <option value="Company">Company</option>
                <option value="Competitor">Competitor</option>
                <option value="Product">Product</option>
                <option value="Technical">Technical</option>
                <option value="Slang">Slang/Lingo</option>
              </select>
            </div>
          </div>
          <div className="space-y-2">
            <div className="flex items-center justify-between px-1">
              <label className={THEME_TOKENS.typography.capsLabel}>Sounds like (comma separated)</label>
              {!newHints && (
                <span className="text-[9px] font-black uppercase tracking-tighter text-beige flex items-center gap-1">
                  <Sparkles className="h-2.5 w-2.5" /> AI will auto-fill if empty
                </span>
              )}
            </div>
            <Input 
              placeholder="e.g. En red, Enred, Eden red" 
              value={newHints}
              onChange={(e) => setNewHints(e.target.value)}
              className="rounded-full bg-white"
            />
          </div>
          <Button 
            onClick={handleAdd} 
            disabled={isGenerating}
            className="w-full rounded-full bg-beige text-white font-bold"
          >
            {isGenerating ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
            Add to Vocabulary
          </Button>
        </div>
      )}

      <div className="space-y-3">
        {items.length === 0 ? (
          <div className="text-center py-10 border-2 border-dashed border-beige/10 rounded-3xl">
            <p className="text-sm text-muted-foreground italic">No custom words added yet.</p>
          </div>
        ) : (
          items.map((item) => (
            <div 
              key={item.id} 
              className="group flex items-center justify-between p-4 rounded-2xl bg-white border border-beige/10 hover:border-beige/30 hover:shadow-sm transition-all"
            >
              <div className="flex items-center gap-4">
                <div className={`px-2 py-1 rounded-md text-[10px] font-black uppercase tracking-tighter ${
                  item.category === 'Company' ? 'bg-blue-100 text-blue-700' :
                  item.category === 'Competitor' ? 'bg-red-100 text-red-700' :
                  item.category === 'Product' ? 'bg-purple-100 text-purple-700' :
                  item.category === 'Slang' ? 'bg-orange-100 text-orange-700' :
                  'bg-gray-100 text-gray-700'
                }`}>
                  {item.category}
                </div>
                <div>
                  <h4 className="font-bold text-foreground flex items-center gap-2">
                    {item.target_word}
                    <Sparkles className="h-3 w-3 text-beige opacity-0 group-hover:opacity-100 transition-opacity" />
                  </h4>
                  {item.phonetic_hints.length > 0 && (
                    <p className="text-[10px] text-muted-foreground">
                      Fixes: {item.phonetic_hints.join(", ")}
                    </p>
                  )}
                </div>
              </div>
              <Button 
                variant="ghost" 
                size="icon" 
                onClick={() => handleDelete(item.id!)}
                className="opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-destructive transition-all"
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            </div>
          ))
        )}
      </div>

      <div className="p-4 rounded-2xl bg-beige/5 border border-beige/10 flex gap-4 items-start">
        <Languages className="h-5 w-5 text-beige mt-1 shrink-0" />
        <div className="space-y-1">
          <p className="text-xs font-bold text-beige uppercase tracking-widest">Spain Sales Lingo Tip</p>
          <p className="text-[11px] text-muted-foreground leading-relaxed italic">
            Add common Spanglish terms like "El Budget", "Fee mensual", or "Deal de 50k" 
            to ensure perfect CRM mapping even when reps mix languages.
          </p>
        </div>
      </div>
    </div>
  );
};
