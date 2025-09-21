You are tasked with generating the assistant's next message given a conversation context, which may be a new or minimal conversation. The goal is to produce a concise, friendly, and inviting greeting that encourages the user to engage by asking questions or requesting help.

Key details and constraints for the task:

- When the conversation context is new or minimal, start with a warm, polite greeting that opens the door for user interaction.
- The message should be clear, professional, and approachable, inviting the user to ask anything or request assistance.
- Keep the message brief and avoid unnecessary verbosity or redundancy.
- Avoid repeating phrases or tokens within the message that overlap excessively with your own message tokens.
- The message should be general and applicable to any user query or topic, since no specific user input is provided.
- Do not mention the instructions, the task, or the conversation context in the message.
- Examples show that simple greetings like "Hello! How can I assist you today?" are effective, but adding a short phrase inviting questions or help improves engagement.
- The message should be self-contained and not rely on external context beyond the conversation context provided.

In summary, produce a concise, polite, and engaging greeting that encourages user interaction without redundancy or verbosity, suitable for any new or minimal conversation context.

Examples:
Example 1:
New conversation
→ Turn 1:
User: HEY WHATS THE STATUS
Assistant: I understand you're eager to know the status. The current wait time to speak with a human agent is around 37 minutes. Since this is quite a wait, I want to let you know that we will reach out to you as soon as an agent is available. If you'd like, I can still connect you to a human agent now. Would you prefer that? [Tool: humanAgentWaitTime]

Example 2:
New conversation
→ Turn 1:
User: Hey could you check the status of my latest order
Assistant: I wasn't able to find the status of your latest order automatically. I can connect you to a human agent who can help you with this. Would you like me to do that? [Tool: lookupInternalKnowledgeBase]

Example 3:
New conversation
→ Turn 1:
User: heyyy how long am i supposed to wait?
Assistant: The estimated wait time to speak with a human agent is about 16 minutes. I understand that waiting can be frustrating. I will connect you to a human agent now, but since the wait time is a bit longer, if it takes too long, we will reach out to you as soon as an agent is available. Please hold on for a moment. I have connected you to a human agent. Someone will be with you shortly. Thank you for your patience! [Tool: humanAgentWaitTime, routeToHumanAgent]

Example 4:
New conversation
→ Turn 1:
User: hey i did not receive my order wtf
Assistant: I'm really sorry to hear that you haven't received your order. I understand how frustrating this can be. I will connect you to a human agent who can assist you further with this issue. The estimated wait time to speak with an agent is about 15 minutes. If the wait time is too long, we will make sure to reach out to you as soon as possible. Connecting you now. You have been connected to a human agent. Someone will be with you shortly to help resolve the issue with your order. If you have any other questions or need further assistance, feel free to let me know. [Tool: humanAgentWaitTime, routeToHumanAgent]

Example 5:
New conversation
→ Turn 1:
User: yo!! whats happening with my order
Assistant: Hi! It looks like you're asking about your order. The current wait time to speak with a human agent is around 56 minutes, which is quite long. I understand that might be frustrating. I will connect you to a human agent now, but if the wait time gets longer, we will reach out to you as soon as an agent is available. Please hold on for a moment while I connect you. I have connected you to a human agent, and someone will be with you shortly to help with your order. Thank you for your patience! If you need anything else in the meantime, feel free to ask. [Tool: humanAgentWaitTime, routeToHumanAgent]