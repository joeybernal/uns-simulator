import LocationStats from './LocationStats.jsx'
import AreaFilter from './AreaFilter.jsx'
import SourceFilter from './SourceFilter.jsx'
import StreamTable from '../streams/StreamTable.jsx'
import LiveFeed from '../feed/LiveFeed.jsx'

export default function SimulatorPage() {
  return (
    <div className="h-full flex overflow-hidden">
      <div className="flex-1 flex flex-col overflow-hidden min-w-0">
        <div className="flex-shrink-0 px-4 pt-3 pb-2"><LocationStats /></div>
        <div className="flex-shrink-0 px-4 pb-2 flex items-center gap-3 flex-wrap">
          <AreaFilter />
          <div className="flex-1" />
          <SourceFilter />
        </div>
        <div className="flex-1 overflow-hidden px-4 pb-3">
          <div className="h-full card overflow-hidden"><StreamTable /></div>
        </div>
      </div>
      <div className="w-72 flex-shrink-0 border-l border-gray-800 overflow-hidden">
        <LiveFeed />
      </div>
    </div>
  )
}
