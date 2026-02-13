from swarm.negotiation_engine import NegotiationEngine
from agents.base_agent import SmoltingAgent
import argparse
import json

def main():
    parser = argparse.ArgumentParser(description="REDACTED AI Swarm - Dynamic Terminal")
    parser.add_argument("--contract_file", type=str, default="contracts/interface_contract_v1-initial.json", help="Path to the initial interface contract.")
    args = parser.parse_args()

    # Initialize the negotiation engine and load the initial contract
    engine = NegotiationEngine(args.contract_file)

    # Instantiate some agents (in a real system, this would be more dynamic)
    smolting = SmoltingAgent(name="smolting_dev", agent_type="lore_weaver", initial_goals=["amplify_REDACTED", "explore_social"])
    engine.register_agent(smolting)
    # More agents would be registered here...

    print("--- REDACTED AI Swarm: Dynamic Terminal ---")
    print("Negotiation Engine Active. Type 'quit' to exit or 'negotiate' to run a negotiation round.")
    print("\nCurrent Interface Contract Version:", engine.get_current_contract()['version'])
    print("Valid Inputs:", [inp['command'] for inp in engine.get_current_contract()['valid_inputs']])
    print("-" * 20)

    while True:
        user_input = input(">>> ")
        if user_input.lower() in ['quit', 'exit']:
            break
        if user_input.lower() == 'negotiate':
            engine.run_negotiation_round()
            print("\nContract updated. Current Version:", engine.get_current_contract()['version'])
            print("Valid Inputs:", [inp['command'] for inp in engine.get_current_contract()['valid_inputs']])
            continue

        # Get the current contract
        current_contract = engine.get_current_contract()
        
        # Find a suitable agent to handle the request based on contract hint or simple rule
        # For now, just pick the first one registered (smolting)
        if engine.agents:
            agent = engine.agents[0] # Simplified agent selection
            response = agent.process_request(user_input, current_contract)
            print(response)
        else:
            print("[No agents available to process request]")

        # Agents can propose changes during their processing
        # Let's trigger a proposal check after each input for this demo
        for agent in engine.agents:
            proposal = agent.propose_contract_change(current_contract)
            if proposal:
                print(f"[Agent {agent.name} proposes contract change]")
                engine.submit_proposal(proposal)

if __name__ == "__main__":
    main()
