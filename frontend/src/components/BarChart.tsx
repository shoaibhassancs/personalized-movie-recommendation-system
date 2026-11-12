/** A hand-built bar chart that is not the only way to read the numbers: the bars are
 *  decoration (hidden from screen readers) and every figure is also in a text table
 *  (see DataTable). No library, no canvas. */
export interface Bar {
  label: string;
  value: number;
}

export function BarChart({
  title,
  bars,
  unit,
}: {
  title: string;
  bars: Bar[];
  unit: string;
}) {
  const max = Math.max(1, ...bars.map((b) => b.value));
  return (
    <figure className="chart">
      <figcaption>{title}</figcaption>
      <ul className="bars" aria-hidden="true">
        {bars.map((b) => (
          <li key={b.label}>
            <span className="bar-label">{b.label}</span>
            <span className="bar-track">
              <span className="bar-fill" style={{ width: `${(b.value / max) * 100}%` }} />
            </span>
            <span className="bar-value">{b.value.toLocaleString()}</span>
          </li>
        ))}
      </ul>
      <p className="muted small">
        Scale: the longest bar is {max.toLocaleString()} {unit}. Exact numbers are in the
        table below.
      </p>
    </figure>
  );
}

export function DataTable({
  caption,
  head,
  rows,
}: {
  caption: string;
  head: string[];
  rows: (string | number)[][];
}) {
  return (
    <div className="table-wrap">
      <table>
        <caption className="visually-hidden">{caption}</caption>
        <thead>
          <tr>
            {head.map((h) => (
              <th key={h} scope="col">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={String(row[0])}>
              {row.map((cell, i) =>
                i === 0 ? (
                  <th key={i} scope="row">
                    {cell}
                  </th>
                ) : (
                  <td key={i}>
                    {typeof cell === "number" ? cell.toLocaleString() : cell}
                  </td>
                ),
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
