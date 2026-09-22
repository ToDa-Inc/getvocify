import { useLanguage } from "@/lib/i18n";
import {
  objectionCategoriesEmptyMessage,
  visibleObjectionCategories,
  type ObjectionCategory,
} from "@/lib/team-insights";

export function ObjectionBreakdown({ categories }: { categories: ObjectionCategory[] }) {
  const { t } = useLanguage();
  const emptyMessage = objectionCategoriesEmptyMessage(categories, t.product.objections);
  const visible = visibleObjectionCategories(categories, t.product.objections);
  const maxCount = visible.reduce((max, item) => Math.max(max, item.count), 0);
  return (
    <section aria-labelledby="team-objections">
      <h2 id="team-objections">Objeciones</h2>
      {emptyMessage ? (
        <p>{emptyMessage}</p>
      ) : (
        <ul className="space-y-3">
          {visible.map((item) => (
            <li key={item.name} className="space-y-1">
              <div className="flex justify-between gap-4 text-sm">
                <span>{item.name}</span>
                <span>{item.count}</span>
              </div>
              <div className="relative h-4 w-full overflow-hidden rounded-full bg-secondary">
                <div
                  className="h-full bg-primary"
                  style={{ width: maxCount > 0 ? `${(item.count / maxCount) * 100}%` : "0%" }}
                />
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
