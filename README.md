# RemitChain: Institutional Cross-Border Remittance Portal

## The Problem
Traditional cross-border remittances are often slow, opaque, and expensive. They rely on fragmented correspondent banking networks (like SWIFT) which can take days to settle and lack transparency for the end-user. Issues like compliance holds, name mismatches, or payout rail failures are typically communicated manually, creating massive operational overhead and a poor user experience.

## The Solution
RemitChain is a modern, API-first remittance orchestrator built for the next generation of instant cross-border payments (mimicking rails like UPI and modern banking infrastructure). 
It features:
- **Instant Settlement Simulation**: Orchestrates the full lifecycle of a transfer (Quote -> Screen -> Fund -> Payout -> Settle).
- **Institutional UI**: A highly professional, flat-design portal built without heavy frameworks.
- **Real-Time Tracking**: WebSockets power a live-updating transaction timeline for absolute transparency.
- **Automated Compliance**: An integrated compliance desk that automatically flags high-risk transfers for manual review based on simulated risk scoring.
- **Demo Scenarios**: Built-in developer tools to intentionally force edge cases (Sanctions Hits, Name Mismatches, Expired Quotes, etc.).

## Getting Started (Local Development)

### Prerequisites
- Python 3.9+
- Git

### Installation

1. **Clone the repository**
   \\\ash
   git clone https://github.com/Ved-2107/NPCI_LATENCY.git
   cd NPCI_LATENCY
   \\\

2. **Set up the Python Virtual Environment**
   Navigate into the \hub\ directory and create a virtual environment:
   \\\ash
   cd hub
   python -m venv .venv
   \\\

3. **Activate the Virtual Environment**
   - **Windows:** \.venv\Scripts\activate\
   - **Mac/Linux:** \source .venv/bin/activate\

4. **Install Dependencies**
   \\\ash
   pip install -r requirements.txt
   pip install websockets uvicorn[standard]
   \\\

### Running the Project

Start the FastAPI orchestrator in in-memory mode:

**Windows (PowerShell):**
\\\powershell
$env:LEDGER_MODE="memory"
uvicorn app.main:app --reload --port 8000
\\\

**Mac/Linux (Bash):**
\\\ash
export LEDGER_MODE="memory"
uvicorn app.main:app --reload --port 8000
\\\

### Access the Application
Once the server is running, open your browser and navigate to:
**http://localhost:8000**

You can immediately start simulating cross-border transactions and view them on the live-updating tracking timeline!
