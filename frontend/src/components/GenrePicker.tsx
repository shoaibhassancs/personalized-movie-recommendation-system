import { GENRES } from "../constants";

interface Props {
  selected: string[];
  onChange: (genres: string[]) => void;
  disabled?: boolean;
}

export function GenrePicker({ selected, onChange, disabled }: Props) {
  const toggle = (genre: string) =>
    onChange(
      selected.includes(genre)
        ? selected.filter((g) => g !== genre)
        : [...selected, genre],
    );
  return (
    <fieldset className="genres" disabled={disabled}>
      <legend>Favourite genres</legend>
      {GENRES.map((genre) => (
        <label key={genre} className="chip">
          <input
            type="checkbox"
            checked={selected.includes(genre)}
            onChange={() => toggle(genre)}
          />
          <span>{genre}</span>
        </label>
      ))}
    </fieldset>
  );
}
