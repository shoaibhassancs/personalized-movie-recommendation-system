import type { Poster as PosterData } from "../api/types";

/** The API's generated placeholder: initials on a colour. No image is fetched. */
export function Poster({
  poster,
  large = false,
}: {
  poster: PosterData;
  large?: boolean;
}) {
  return (
    <div
      className={large ? "poster poster-large" : "poster"}
      style={{ backgroundColor: `hsl(${poster.hue} 40% 32%)` }}
      aria-hidden="true"
    >
      {poster.initials}
    </div>
  );
}
