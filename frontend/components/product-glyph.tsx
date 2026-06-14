/**
 * ProductGlyph — the SVG product stand-ins lifted from the v2 design files.
 * Used wherever a real photo / GLB isn't present (marketplace thumbs, decision
 * cards, the reveal stage fallback). Keyed by a simple `kind` string that maps
 * to seed `thumb_key` values.
 */
export function ProductGlyph({
  kind,
  className,
}: {
  kind: string;
  className?: string;
}) {
  switch (kind) {
    case "monitor":
      return (
        <svg viewBox="0 0 160 90" className={className} aria-hidden>
          <rect x="40" y="20" width="80" height="52" rx="9" fill="#f3f3f5" />
          <circle cx="80" cy="46" r="15" fill="#26262a" />
          <circle cx="80" cy="46" r="6" fill="#FF9900" />
          <rect x="74" y="8" width="12" height="10" rx="3" fill="#cfcfd4" />
        </svg>
      );
    case "earbuds":
      return (
        <svg viewBox="0 0 120 70" className={className} aria-hidden>
          <rect x="40" y="20" width="40" height="32" rx="14" fill="#f1f1f4" />
          <rect x="46" y="14" width="8" height="14" rx="4" fill="#cfcfd4" />
          <rect x="66" y="14" width="8" height="14" rx="4" fill="#cfcfd4" />
        </svg>
      );
    case "books":
      return (
        <svg viewBox="0 0 120 70" className={className} aria-hidden>
          <rect x="36" y="16" width="48" height="40" rx="3" fill="#f1f1f4" />
          <rect x="36" y="16" width="48" height="8" fill="#FF9900" />
        </svg>
      );
    case "shoe":
    default:
      return (
        <svg viewBox="0 0 200 110" className={className} aria-hidden>
          <ellipse cx="100" cy="96" rx="74" ry="6" fill="rgba(0,0,0,.4)" />
          <path
            d="M26 84 Q29 98 46 98 L172 98 Q186 98 185 86 L182 78 L28 78 Z"
            fill="#e9e9ec"
          />
          <path
            d="M30 80 C33 56 50 40 76 38 C93 36 102 28 112 20 C124 11 138 9 150 17 C156 22 159 29 163 38 C171 56 186 64 189 80 Z"
            fill="#fbfbfc"
          />
          <path
            d="M60 74 C92 69 134 56 162 38 C158 50 150 60 138 66 C114 76 80 78 60 74 Z"
            fill="#FF9900"
          />
        </svg>
      );
  }
}
