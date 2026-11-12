const VALUES = [0.5, 1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5, 5];

interface Props {
  value: number | null;
  disabled?: boolean;
  onChange: (rating: number) => void;
  onClear: () => void;
}

/** Half-star rating as ten buttons (works with the keyboard). It shows the value the
 *  server last returned, never a guess. */
export function StarRating({ value, disabled, onChange, onClear }: Props) {
  return (
    <fieldset className="rating" disabled={disabled}>
      <legend>Your rating</legend>
      <p className="rating-now" aria-live="polite">
        {value === null ? "Not rated" : `★ ${value} of 5`}
      </p>
      <div className="rating-buttons" role="group" aria-label="Choose a rating">
        {VALUES.map((v) => (
          <button
            key={v}
            type="button"
            className="toggle"
            aria-pressed={value === v}
            aria-label={`${v} ${v === 1 ? "star" : "stars"}`}
            onClick={() => onChange(v)}
          >
            {v}
          </button>
        ))}
      </div>
      <button type="button" className="link" onClick={onClear} disabled={value === null}>
        Clear rating
      </button>
    </fieldset>
  );
}
