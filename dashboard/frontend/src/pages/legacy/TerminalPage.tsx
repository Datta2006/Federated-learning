import { useState, useRef, useEffect } from 'react'
import { Send, Copy, Download, History as HistoryIcon } from 'lucide-react'

interface Command {
  id: string
  command: string
  output?: string
  timestamp: Date
}

export function TerminalPage() {
  const [input, setInput] = useState('')
  const [commands, setCommands] = useState<Command[]>([])
  const [loading, setLoading] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const outputRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    // Add welcome message
    if (commands.length === 0) {
      addCommand('dashboard stats', 'Welcome to AirFed Terminal\nType commands to interact with the dashboard API')
    }
  }, [])

  const addCommand = (command: string, output: string) => {
    const newCmd: Command = {
      id: Date.now().toString(),
      command,
      output,
      timestamp: new Date(),
    }
    setCommands(prev => [...prev, newCmd])
    
    // Auto-scroll to bottom
    setTimeout(() => {
      outputRef.current?.scrollTo({
        top: outputRef.current.scrollHeight,
        behavior: 'smooth'
      })
    }, 100)
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!input.trim()) return

    setLoading(true)
    
    // Simulate API response
    setTimeout(() => {
      let response = ''
      
      switch (input.toLowerCase()) {
        case '/status':
          response = '{\"status\": \"healthy\", \"uptime\": \"2d 4h 32m\", \"workers\": 42, \"rounds\": 128}'
          break
        case '/workers':
          response = '{\"online\": 38, \"offline\": 4, \"busy\": 12, \"total\": 42}'
          break
        case '/rounds':
          response = '{\"current\": 128, \"total\": 500, \"phase\": \"evaluation\", \"progress\": \"87%\"}'
          break
        case '/model':
          response = '{\"version\": \"federated_v3.2\", \"params\": 12800000, \"val_loss\": 0.0423, \"samples\": 84200}'
          break
        case '/help':
          response = 'Available commands:\n/status - System status\n/workers - Worker details\n/rounds - Current round info\n/model - Latest model info\n/help - Show this help'
          break
        default:
          response = `Unknown command: ${input}\nType /help for available commands`
      }

      addCommand(input, response)
      setLoading(false)
      setInput('')
    }, 300)
  }

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text)
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Terminal</h1>
        <p className="text-muted-foreground mt-1">
          Live API command execution and system inspection
        </p>
      </div>

      {/* Terminal Output */}
      <div className="panel">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-medium text-foreground">Terminal Output</h3>
          <div className="flex gap-2">
            <button className="btn btn-secondary btn-sm flex items-center gap-1">
              <HistoryIcon size={14} /> History
            </button>
            <button className="btn btn-secondary btn-sm flex items-center gap-1">
              <Download size={14} /> Export
            </button>
          </div>
        </div>
        
        <div 
          ref={outputRef}
          className="bg-black/50 rounded-lg p-4 font-mono text-sm text-foreground max-h-96 overflow-y-auto"
        >
          {commands.map((cmd) => (
            <div key={cmd.id} className="space-y-1">
              <div className="flex items-center gap-2">
                <span className="text-primary">&gt;</span>
                <span className="text-white">{cmd.command}</span>
              </div>
              <pre className="text-muted-foreground whitespace-pre-wrap">
                {cmd.output}
              </pre>
            </div>
          ))}
          
          {loading && (
            <div className="flex items-center gap-2">
              <span className="text-primary">&gt;</span>
              <span className="text-muted-foreground">...</span>
            </div>
          )}
        </div>
      </div>

      {/* Command Input */}
      <div>
        <form onSubmit={handleSubmit} className="flex gap-2">
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Type a command (e.g., /status, /help)..."
            className="input flex-1 font-mono"
            disabled={loading}
            autoComplete="off"
          />
          <button 
            type="submit" 
            disabled={loading || !input.trim()}
            className="btn btn-primary"
          >
            <Send size={16} />
          </button>
        </form>
        
        <div className="text-xs text-muted-foreground mt-2">
          Press <kbd className="px-1 py-0.5 bg-muted rounded">Tab</kbd> for autocomplete
        </div>
      </div>

      {/* Recent Commands */}
      {commands.length > 1 && (
        <div className="panel">
          <h3 className="font-medium text-foreground mb-3">Recent Commands</h3>
          <div className="space-y-2">
            {commands.slice(-5).reverse().map((cmd) => (
              <button
                key={cmd.id}
                onClick={() => setInput(cmd.command)}
                className="w-full text-left px-3 py-2 rounded bg-muted/20 hover:bg-muted/30 flex items-center gap-2 text-sm"
              >
                <span className="text-muted-foreground">&gt;</span>
                <kbd className="px-2 py-0.5 bg-border rounded text-xs mono">{cmd.command}</kbd>
                <Copy size={14} className="text-muted-foreground ml-auto" />
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}