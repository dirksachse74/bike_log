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
        Bike Log {meta.version} · database schema {meta.schema} · app commit <code>{meta.commit}</code> · screens commit <code>{meta.ui_commit}</code>
      </p>
    </>
  )
}
