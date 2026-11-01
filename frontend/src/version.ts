// Which code is running. Three commits must agree: the app (backend), the screens it bundles
// (frontend/dist) and the screens this browser tab loaded. A mismatch explains "I updated but
// still see the old screen" and says what to do.
const known = (c: string) => c && c !== 'unknown'

// Which code is running. Three commits must agree: the app (backend), the screens it bundles
// (frontend/dist) and the screens this browser tab loaded. A mismatch explains "I updated but
// still see the old screen" and says what to do.
export function versionProblem(meta: { commit: string; ui_commit: string }): string | null {
  if (known(meta.commit) && known(meta.ui_commit) && meta.commit !== meta.ui_commit)
    return `The screens inside this app were built from an older state of the code (${meta.ui_commit}) than the app itself (${meta.commit}). Rebuild: close Bike Log, run "npm run build" in the frontend folder, then PyInstaller and the installer again (see UPDATING.md).`
  if (known(__BUILD_COMMIT__) && known(meta.ui_commit) && __BUILD_COMMIT__ !== meta.ui_commit)
    return `This browser tab still shows old screens (${__BUILD_COMMIT__}); the app has ${meta.ui_commit}. Press Ctrl+F5 to reload.`
  return null
}
