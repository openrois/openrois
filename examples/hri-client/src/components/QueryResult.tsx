import type { Result } from "@openrois/interfaces";

interface QueryResultProps {
  results: Result[];
  loading: boolean;
  error: string | null;
}

/**
 * Render a Result[] array as a table.
 *
 * Each result has name, data_type_ref, and value. The value is a
 * string (may be JSON). Display it as-is.
 */
export function QueryResult({ results, loading, error }: QueryResultProps) {
  if (loading) return <div className="query-result empty">Loading...</div>;
  if (error) return <div className="query-result error">{error}</div>;
  if (results.length === 0)
    return <div className="query-result empty">No results</div>;

  return (
    <table className="query-result">
      <thead>
        <tr>
          <th>Name</th>
          <th>Type</th>
          <th>Value</th>
        </tr>
      </thead>
      <tbody>
        {results.map((r, i) => (
          <tr key={i}>
            <td>{r.name}</td>
            <td>{r.data_type_ref}</td>
            <td className="value">{r.value}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}