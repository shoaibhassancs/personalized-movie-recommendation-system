interface Props {
  page: number;
  pageSize: number;
  total: number;
  onPage: (page: number) => void;
}

export function Pager({ page, pageSize, total, onPage }: Props) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  return (
    <nav className="pager" aria-label="Pages">
      <button type="button" disabled={page <= 1} onClick={() => onPage(page - 1)}>
        Previous
      </button>
      <span>
        Page {page} of {pages} · {total} movies
      </span>
      <button type="button" disabled={page >= pages} onClick={() => onPage(page + 1)}>
        Next
      </button>
    </nav>
  );
}
