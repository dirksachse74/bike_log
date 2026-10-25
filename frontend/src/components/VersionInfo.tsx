import { useApp } from '../context'
import { versionProblem } from '../version'

export default function VersionInfo() {
  const { meta } = useApp()
  const problem = versionProblem(meta)
  return (
    <>
      {problem && (
        <p className="form-error" role="alert">
          {problem}
        </p>
      )}
      <p className="small muted">
        <strong>Bike Log {meta.full_version}</strong>
        {meta.release ? ' (release)' : ' (build between releases; the part after + is the commit)'} · database schema {meta.schema} · app commit <code>{meta.commit}</code> · screens
        commit <code>{meta.ui_commit}</code>
      </p>
    </>
  )
}
