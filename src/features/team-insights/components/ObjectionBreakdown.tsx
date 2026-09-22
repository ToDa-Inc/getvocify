import {
  objectionCategoriesEmptyMessage,
  visibleObjectionCategories,
  type ObjectionCategory,
} from "@/lib/team-insights";

export function ObjectionBreakdown({ categories }: { categories: ObjectionCategory[] }) {
  const emptyMessage = objectionCategoriesEmptyMessage(categories);
  const visible = visibleObjectionCategories(categories);
  return (
    <section aria-labelledby="team-objections">
      <h2 id="team-objections">Objeciones</h2>
      {emptyMessage ? (
        <p>{emptyMessage}</p>
      ) : (
        <ul>
          {visible.map((item) => (
            <li key={item.name}>{item.name}</li>
          ))}
        </ul>
      )}
    </section>
  );
}
