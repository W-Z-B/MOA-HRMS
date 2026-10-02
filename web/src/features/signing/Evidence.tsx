import type { SignatureEvidence } from "../../api/types";
import { dmyTime } from "../../app/format";

/** The evidence of a signature in words, with whether the file still matches what was signed. */
export function Evidence({ evidence }: { evidence: SignatureEvidence }) {
  return (
    <dl className="terms evidence" aria-label="Evidence of the signature">
      <dt>Signed</dt>
      <dd>
        {evidence.signer_name}, {dmyTime(evidence.signed_at)}
      </dd>
      <dt>Agreed to</dt>
      <dd>“{evidence.statement}”</dd>
      <dt>Document</dt>
      <dd>
        {evidence.document_title}, version {evidence.document_version}
      </dd>
      <dt>How</dt>
      <dd>
        {evidence.method}, on {evidence.device}
        {evidence.source_ip ? ` from ${evidence.source_ip}` : ""}
      </dd>
      <dt>Fingerprint</dt>
      <dd>
        <code className="fingerprint">{evidence.sha256}</code>{" "}
        {evidence.file_unchanged ? (
          <span className="chip chip-step-done">The file still matches</span>
        ) : (
          <span className="chip chip-career-blocked">The file has changed since it was signed</span>
        )}
      </dd>
    </dl>
  );
}
