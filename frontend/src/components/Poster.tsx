import type { CSSProperties } from "react";
import type { Poster as PosterData } from "../api/types";

/** The API's generated placeholder: initials on a colour. No image is fetched.
 *  The hue goes to the stylesheet as a variable, which draws the gradient. */
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
      style={{ "--hue": poster.hue } as CSSProperties}
      aria-hidden="true"
    >
      <span>{poster.initials}</span>
    </div>
  );
}
