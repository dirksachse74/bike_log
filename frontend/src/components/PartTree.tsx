// Parts made of parts: each part that carries others unfolds to them (wheelset → front / rear wheel →
// hub, tire, spokes ...; crankset → chainrings; rear derailleur → pulley wheels). Every name links to its page.
import { Link } from 'react-router-dom'
import { slotName, usageText } from '../format'
import type { PartNode } from '../types'
import { Tag } from './ui'

const count = (n: PartNode): number => n.children.reduce((s, c) => s + 1 + count(c), 0)

function NodeLine({ n }: { n: PartNode }) {
  return (
    <>
      <span className="muted small">{slotName(n.slot)}</span> <Link to={`/inventory/${n.component_id}`}>{n.label}</Link>{' '}
      <span className="muted small">
        {usageText(n.usage)}
        {n.on ? ` · on ${n.on}` : ''}
      </span>
      {n.due > 0 && (
        <>
          {' '}
          <Tag tone="warn">{n.due} need attention</Tag>
        </>
      )}
    </>
  )
}

export default function PartTree({ nodes, open = false }: { nodes: PartNode[]; open?: boolean }) {
  return (
    <ul className="part-tree">
      {nodes.map((n) => (
        <li key={n.component_id} data-part={n.label}>
          {n.children.length ? (
            <details open={open}>
              <summary>
                <NodeLine n={n} /> <span className="muted small">· {count(n)} part{count(n) === 1 ? '' : 's'} on it</span>
              </summary>
              <PartTree nodes={n.children} />
            </details>
          ) : (
            <NodeLine n={n} />
          )}
        </li>
      ))}
    </ul>
  )
}
