import type { RecommendationsOut } from "../api/types";

/** What to tell the person about HOW this list was made. The API's own sentence
 *  (`branch_reason`) is always shown word for word; the heading and hint only say whether
 *  it is a popularity fallback or a personalised blend, never that it is good for them. */
export function BranchBanner({ rec }: { rec: RecommendationsOut }) {
  const fallback =
    rec.branch === "no_ratings" ||
    rec.branch === "few_ratings" ||
    rec.strategy === "popularity";
  const single = rec.strategy !== "hybrid";
  let title: string;
  let hint: string | null = null;
  if (single) {
    title = `Single method: ${rec.strategy.replace("_", "-")}`;
    if (rec.strategy === "popularity") {
      hint = "The same ranking for everyone: it does not use your ratings or genres.";
    }
  } else if (rec.branch === "no_ratings") {
    title = "Not personalised from your ratings";
    hint = "Rate some movies and this page can start to use them.";
  } else if (rec.branch === "few_ratings") {
    title = "Popularity fallback: not personalised";
    hint = "With only a few ratings the app falls back to popular movies.";
  } else {
    title = `Blend built from your ${rec.rating_count} ratings`;
    hint = "A blend of several methods. It does not tell you that you will like these.";
  }
  return (
    <section
      className={fallback ? "notice notice-info" : "notice notice-plain"}
      aria-label="How this list was made"
    >
      <h2 className="notice-title">{title}</h2>
      <p>{rec.branch_reason}</p>
      {hint && <p className="muted small">{hint}</p>}
    </section>
  );
}

export function RecommendationNotes({ notes }: { notes: string[] }) {
  if (notes.length === 0) return null;
  return (
    <ul className="notes" aria-label="Notes about this list">
      {notes.map((n) => (
        <li key={n}>{n}</li>
      ))}
    </ul>
  );
}

/** The API's model notice, verbatim: the serving model has no quality metric of its own
 *  and the Step 16 results describe a different, separately fitted model. */
export function ModelNotice({ text }: { text: string }) {
  return (
    <aside className="model-notice" aria-label="About these recommendations">
      <h3>About these recommendations</h3>
      <p>{text}</p>
    </aside>
  );
}
