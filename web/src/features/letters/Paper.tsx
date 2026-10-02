import type { LetterPreview, LetterRun } from "../../api/types";

function Runs({ runs }: { runs: LetterRun[] }) {
  return (
    <>
      {runs.map((run, i) => (run.bold ? <strong key={i}>{run.text}</strong> : <span key={i}>{run.text}</span>))}
    </>
  );
}

/** A letter as it will read once issued: who it is to, its subject, and its wording with the fields filled. */
export function Paper({ letter }: { letter: LetterPreview }) {
  const v = letter.values;
  const to = [v.full_name, v.post_title, [v.unit, v.campus].filter(Boolean).join(", ")].filter(Boolean);
  return (
    <article className="letter-paper" aria-label="The letter">
      {letter.addressed && (
        <p className="to">
          {to.map((line, i) => (
            <span key={i}>
              {i > 0 && <br />}
              {line}
            </span>
          ))}
        </p>
      )}
      <p className="subject">{letter.subject}</p>
      {letter.blocks.map((block, i) =>
        block.type === "list" ? (
          <ul key={i}>
            {block.items.map((item, j) => (
              <li key={j}>
                <Runs runs={item} />
              </li>
            ))}
          </ul>
        ) : (
          <p key={i}>
            {block.lines.map((line, j) => (
              <span key={j}>
                {j > 0 && <br />}
                <Runs runs={line} />
              </span>
            ))}
          </p>
        ),
      )}
    </article>
  );
}
