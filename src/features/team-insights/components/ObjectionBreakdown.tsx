import { useLanguage } from "@/lib/i18n";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import {
  objectionCategoriesEmptyMessage,
  objectionResolutionCountsText,
  visibleObjectionCategories,
  type CompetitorMention,
  type ObjectionCategory,
} from "@/lib/team-insights";

export function ObjectionBreakdown({
  categories,
  competitors,
  sampleLimited,
}: {
  categories: ObjectionCategory[];
  competitors?: CompetitorMention[];
  sampleLimited?: boolean;
}) {
  const { t } = useLanguage();
  const p = t.product;
  const emptyMessage = objectionCategoriesEmptyMessage(categories, p.objections, p.teamObjectionsEmptyWeek);
  const visible = visibleObjectionCategories(categories, p.objections);
  const namedCompetitors = (competitors ?? []).filter((item) => item.count > 0);
  const maxCount = visible.reduce((max, item) => Math.max(max, item.count), 0);
  const showCompetitors = namedCompetitors.length > 0;
  if (emptyMessage && !showCompetitors) {
    return (
      <section aria-labelledby="team-objections" className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-5 space-y-4`}>
        <h2 id="team-objections" className={THEME_TOKENS.typography.sectionTitle}>{p.teamHeadingObjections}</h2>
        <p>{emptyMessage}</p>
      </section>
    );
  }
  return (
    <section aria-labelledby="team-objections" className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-5 space-y-4`}>
      <h2 id="team-objections" className={THEME_TOKENS.typography.sectionTitle}>{p.teamHeadingObjections}</h2>
      {emptyMessage ? <p>{emptyMessage}</p> : null}
      {visible.length > 0 ? (
        <>
          <ul className="space-y-3">
            {visible.map((item) => (
              <li key={item.name} className="space-y-1">
                <div className="flex justify-between gap-4 text-sm">
                  <span>{item.name}</span>
                  <span>
                    {item.count} {objectionResolutionCountsText(item, p)}
                  </span>
                </div>
                <div className="relative h-4 w-full overflow-hidden rounded-full bg-secondary">
                  <div
                    className="h-full bg-primary"
                    style={{ width: maxCount > 0 ? `${(item.count / maxCount) * 100}%` : "0%" }}
                  />
                </div>
                {item.how_to ? (
                  <p className="text-sm text-muted-foreground">
                    <span className={THEME_TOKENS.typography.capsLabel}>{p.objectionHowTo}: </span>
                    {item.how_to}
                  </p>
                ) : null}
                {item.best_example ? (
                  <p className="text-sm text-muted-foreground">
                    <span className={THEME_TOKENS.typography.capsLabel}>{p.objectionBestExample}: </span>
                    {p.prospectQuote.replace("{quote}", item.best_example)}
                  </p>
                ) : null}
              </li>
            ))}
          </ul>
          <div className="sr-only">
          <table>
            <caption>{p.teamHeadingObjections}</caption>
            <thead>
              <tr>
                <th scope="col">{p.teamTableCategory}</th>
                <th scope="col">{p.teamTableCount}</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((item) => (
                <tr key={`table-${item.name}`}>
                  <th scope="row">{item.name}</th>
                  <td>{item.count}. {objectionResolutionCountsText(item, p)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        </>
      ) : null}
      {showCompetitors ? (
        <>
          <p className={THEME_TOKENS.typography.capsLabel}>{p.teamCompetitorsMentioned}</p>
          <ul className="space-y-1 text-sm">
            {namedCompetitors.map((item) => (
              <li key={item.name} className="space-y-1">
                <div className="flex justify-between gap-4">
                  <span>{item.name}</span>
                  <span>{item.count}</span>
                </div>
                {(item.quotes ?? []).slice(0, 1).map((mention) => (
                  <p key={mention.date} className="text-sm text-muted-foreground">
                    {p.prospectQuote.replace("{quote}", mention.quote)}
                  </p>
                ))}
              </li>
            ))}
          </ul>
          <div className="sr-only">
          <table>
            <caption>{p.teamCompetitorsMentioned}</caption>
            <thead>
              <tr>
                <th scope="col">{p.teamTableName}</th>
                <th scope="col">{p.teamTableCount}</th>
              </tr>
            </thead>
            <tbody>
              {namedCompetitors.map((item) => (
                <tr key={`competitor-${item.name}`}>
                  <th scope="row">{item.name}</th>
                  <td>{item.count}</td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        </>
      ) : null}
      {sampleLimited && showCompetitors ? <p className={THEME_TOKENS.typography.body}>{p.sampleLimited}</p> : null}
    </section>
  );
}
