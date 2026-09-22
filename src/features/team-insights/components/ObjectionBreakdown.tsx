export function ObjectionBreakdown({ categories }: { categories: Array<{ name: string; count: number }> }) {
  const ordered = [...categories].sort((a, b) => b.count - a.count || a.name.localeCompare(b.name, "es"));
  return (
    <section aria-labelledby="team-objections">
      <h2 id="team-objections">Objeciones</h2>
      <table>
        <tbody>
          {ordered.map((item) => (
            <tr key={item.name}><th>{item.name}</th><td>{item.count}</td></tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
