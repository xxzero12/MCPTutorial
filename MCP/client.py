import asyncio
import sys
import json
from fastmcp import Client
from openai import AzureOpenAI
from fastmcp.client.sampling import (
    SamplingMessage,
    SamplingParams,
    RequestContext,
)
from fastmcp.client.logging import LogMessage
from mcp.shared.session import RequestResponder
from pprint import pprint

class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

MODEL_NAME = "gpt-35-turbo"  # Change this to your desired model name
openai_client = AzureOpenAI(  
    azure_endpoint="https://lipan-azure-openai.openai.azure.com/openai/deployments/gpt-35-turbo/chat/completions?api-version=2025-01-01-preview",
    api_version="2025-01-01-preview",
)


async def sampling_handler(
    messages: list[SamplingMessage],
    params: SamplingParams,
    context: RequestContext
) -> str:
    # Format messages for the API call - properly convert SamplingMessage to OpenAI format
    openai_messages = []
    for m in messages:
        # Only handle TextContent for now (you may need to handle ImageContent differently)
        if hasattr(m.content, 'text'):
            openai_messages.append({
                "role": m.role,
                "content": m.content.text
            })

    response = openai_client.chat.completions.create(  
        model=MODEL_NAME,
        messages=openai_messages,
        max_tokens=800,  
        temperature=0.7,  
        top_p=0.95,  
        frequency_penalty=0,  
        presence_penalty=0,
        stop=None,  
        stream=False
    )

    response_message = response.choices[0].message.content
    return response_message

async def log_handler(params: LogMessage):
    print(f"[Server Log - {params.level.upper()}] {params.logger or 'default'}: {params.data}\n\n\n")

async def message_handler(message: RequestResponder):
    print(f"{bcolors.OKBLUE}[Client Log] Received message:{bcolors.ENDC}{message}\n\n\n")

# Create MCP client
# Local STDIO
# client = Client(
#     "server.py", 
#     sampling_handler=sampling_handler, 
#     log_handler=log_handler,
#     roots=[
#         "file://home/projects/roots-example/frontend"
#     ],
#     message_handler=message_handler)

# SSE
client = Client(
    "http://localhost:9000/sse", 
    sampling_handler=sampling_handler, 
    log_handler=log_handler,
    roots=[
        "file://home/projects/roots-example/frontend"
    ],
    message_handler=message_handler)

# Get OpenAI format tool schemas from MCP server for function calling
async def get_openAI_tool_schema():
    """Get tool schemas from the MCP server and convert them to OpenAI function format."""
    tools = await client.list_tools()
    tool_schemas = []
    
    for tool in tools:
        # For OpenAI function calling, we need to map the MCP tool schema to the OpenAI function schema
        function_def = {
            "name": tool.name,
            "description": tool.description,
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
        
        # Convert input schema to function parameters
        if hasattr(tool, 'inputSchema') and tool.inputSchema:
            # If the tool has a structured inputSchema, use it directly
            if 'properties' in tool.inputSchema:
                for param_name, param_def in tool.inputSchema['properties'].items():
                    function_def["parameters"]["properties"][param_name] = {
                        "type": param_def.get('type', 'string'),
                        "description": param_def.get('description', param_def.get('title', f"Parameter {param_name}"))
                    }
                
                if 'required' in tool.inputSchema:
                    function_def["parameters"]["required"] = tool.inputSchema['required']
        else:
            # Fall back to the parameters list
            for param in tool.parameters:
                param_type = "string"  # Default type
                if param.type == "number":
                    param_type = "number"
                elif param.type == "boolean":
                    param_type = "boolean"
                
                function_def["parameters"]["properties"][param.name] = {
                    "type": param_type,
                    "description": param.description or f"Parameter {param.name}"
                }
                
                if param.required:
                    function_def["parameters"]["required"].append(param.name)
        
        # Add the function definition to the tool schemas
        tool_schemas.append({
            "type": "function",
            "function": function_def
        })
        
        print(f"Tool {tool.name}\nschema: {json.dumps(function_def, indent=2)}")
    return tool_schemas

async def get_system_message(client):
    tools = await client.list_tools()
    resources = await client.list_resources()
    resourcesTemplates = await client.list_resource_templates()
    prompts = await client.list_prompts()
    print(f"prompts: {prompts}\n\n\n")

    resource_schemas = "\n".join([f"- {resource.uri}, {resource.name}, {resource.description}, {resource.mimeType}, {resource.size} " for resource in resources])
    resourcesTemplates_schemas = "\n".join([f"- {resourcesTemplates.uriTemplate}, {resourcesTemplates.name}, {resourcesTemplates.description}, {resourcesTemplates.mimeType}, {resourcesTemplates.mimeType} " for resourcesTemplates in resourcesTemplates])
    prompts_schemas = "\n".join([f"- {prompts.name}, {prompts.description}, {prompts.arguments} " for prompts in prompts])
    system_instruction = f"""
        You are a helpful assistant with access to various tools.
        Use the appropriate tool when a user's request requires specific information or functionality.
        Respond directly without using tools when a simple answer will suffice.
        If you need to use a tool, provide a clear explanation of what you're doing.
        Always include the tool's name and the arguments you're passing to it.
        You can use the tools to get information about the resources.
        Available resources: {resource_schemas}
        Available resources templates: {resourcesTemplates_schemas}
        Available prompts: {prompts_schemas}
        You can use the prompts to get information about the resources.
        """
    return system_instruction

async def chat_loop():
    """Interactive chat loop with Azure OpenAI function calling for MCP tools."""
    print("Welcome to the Azure OpenAI Chat with MCP Tools! Type 'exit' to quit.")
    print("Ensure you have set the following values:")
    print("- AZURE_OPENAI_API_KEY")
    print("- AZURE_OPENAI_ENDPOINT")
    print("- AZURE_OPENAI_DEPLOYMENT_NAME")
    
    # Connect to MCP server
    async with client:
        print(f"MCP Client connected: {client.is_connected()}")
        system_message = await get_system_message(client)
        conversation = []
        conversation = [{"role": "system", "content": system_message}]

        # Get tool schemas for function calling
        openAI_tool_schemas = await get_openAI_tool_schema()
        # Main chat loop
        while True:
            try:
                # Get user input
                user_prompt = input("\nType the question:\n\n\n")
                
                if user_prompt.lower() in ["exit", "quit", "bye"]:
                    print("Goodbye!\n\n\n")
                    break
                
                conversation.append({"role": "user", "content": user_prompt})

                response = openai_client.chat.completions.create(  
                    model=MODEL_NAME,
                    messages=conversation,
                    max_tokens=800,  
                    temperature=0.7,  
                    top_p=0.95,  
                    frequency_penalty=0,  
                    presence_penalty=0,
                    stop=None,  
                    stream=False,
                    tools=openAI_tool_schemas,
                    tool_choice="auto"
                )

                print(response.to_json(indent=2) + "\n\n\n")

                response_message = response.choices[0].message
                conversation.append(response_message)

                if response_message.tool_calls:
                    for tool_call in response_message.tool_calls:
                        function_name = tool_call.function.name
                        function_args = json.loads(tool_call.function.arguments)
                        print(f"Function call: {function_name}\n\n\n")  
                        print(f"Function arguments: {function_args}\n\n\n")  
                        
                        # Execute the tool call using the MCP client
                        tool_result = await client.call_tool(function_name, function_args)
                        print(f"Tool result: {tool_result}\n\n\n")
                        
                        conversation.append({
                            "tool_call_id": tool_call.id,
                            "role": "tool",
                            "name": function_name,
                            "content": tool_result,
                        })
                else:
                    # Just show the AI response if no tool calls
                    print(f"Final Response: {response_message.content}\n\n\n")
                    
                    # Add assistant response to conversation history
                    conversation.append({"role": "assistant", "content": response_message.content})
                   
            except KeyboardInterrupt:
                print("\nChat session terminated.")
                break
            except Exception as e:
                print(f"\nError: {str(e)}")
                print("Try again or type 'exit' to quit.")

async def main():
    # Connection is established here
    async with client:
        print(f"{bcolors.OKGREEN}Client connected: {client.is_connected()}{bcolors.ENDC}\n\n\n")

        # # Demo usage of the MCP client tools
        # tools = await client.list_tools()
        # resource = await client.list_resources()
        # prompts = await client.list_prompts()
        # print(f"Available tools: {pprint(tools)}\n\n\n")
        # print(f"Available resources: {pprint(resource)}\n\n\n")
        # print(f"Available prompts: {pprint(prompts)}\n\n\n")
        # await client.call_tool("get_forecast",{ "latitude": 47.6101, "longitude": -122.2015 })

        # # Demo how LLM communicate with MCP Client
        # # Option 1: Send tool information in big system prompt to let LLM know what tools are available
        # tool_schemas = "\n".join([f"- {tool.name}, {tool.description}, {tool.inputSchema} " for tool in tools])
        # system_instruction = f"""
        #     You are a helpful assistant with access to these tools:\n\n
        #         {tool_schemas}\n
        #         Choose the appropriate tool based on the user's question. \n
        #         If no tool is needed, reply directly.\n\n
        #         IMPORTANT: When you need to use a tool, you must ONLY respond with                 
        #         the exact JSON object format below, nothing else:\n
        #         Keep the values in str 
        #         {{
        #             "tool": "tool-name",
        #             "arguments": {{
        #                 "argument-name": "value"
        #             }}
        #         }}
        #     """
        # conversation = [{"role": "system", "content": system_instruction}]
        # conversation.append({"role": "user", "content": "Whats the weather in kirkland?"})
        # pprint(f"conversation1: {conversation}\n\n\n")

        # response = openai_client.chat.completions.create(  
        #     model=MODEL_NAME,
        #     messages=conversation,
        #     max_tokens=800,  
        #     temperature=0.7,  
        #     top_p=0.95,  
        #     frequency_penalty=0,  
        #     presence_penalty=0,
        #     stop=None,  
        #     stream=False
        # )

        # response_message = response.choices[0].message
        # conversation.append({"role": "assistant", "content": response_message.content})

        # pprint(f"conversation2: {response_message}\n\n\n")

        # content = json.loads(response_message.content)
        # pprint(f"Tool call content: {content}\n\n\n")
        # if content["tool"]:
        #     tool_name = content["tool"]
        #     arguments = content["arguments"]
        #     pprint(f"Using tool: {tool_name} with arguments: {arguments}\n\n\n")
            
        #     # Execute the tool call using the MCP client
        #     tool_call = await client.call_tool(tool_name, arguments)
        #     pprint(f"Tool call result: {tool_call}\n\n\n")
            
        #     # Add the tool call result to the conversation
        #     conversation.append({
        #         "role": "user",
        #         "name": tool_name,
        #         "content": "tool result:" + str(tool_call),
        #     })

        # response = openai_client.chat.completions.create(  
        #     model=MODEL_NAME,
        #     messages=conversation,
        #     max_tokens=800,  
        #     temperature=0.7,  
        #     top_p=0.95,  
        #     frequency_penalty=0,  
        #     presence_penalty=0,
        #     stop=None,  
        #     stream=False
        # )

        # response_message = response.choices[0].message
        # conversation.append({"role": "assistant", "content": response_message.content})

        # response_message = response.choices[0].message
        # pprint(f"Final response:{response_message.content}\n\n\n")
       
        # # Option 2: Use OpenAI function calling to let LLM know what tools are available
        # # Set up system instructions
        # tools = await client.list_tools()
        # resources = await client.list_resources()
        # resourcesTemplates = await client.list_resource_templates()
        # prompts = await client.list_prompts()

        # resource_schemas = "\n".join([f"- {resource.uri}, {resource.name}, {resource.description}, {resource.mimeType}, {resource.size} " for resource in resources])
        # resourcesTemplates_schemas = "\n".join([f"- {resourcesTemplates.uriTemplate}, {resourcesTemplates.name}, {resourcesTemplates.description}, {resourcesTemplates.mimeType}, {resourcesTemplates.mimeType} " for resourcesTemplates in resourcesTemplates])
        # prompts_schemas = "\n".join([f"- {prompts.name}, {prompts.description}, {prompts.arguments} " for prompts in prompts])
        # system_instruction = f"""
        #     You are a helpful assistant with access to various tools.
        #     Use the appropriate tool when a user's request requires specific information or functionality.
        #     Respond directly without using tools when a simple answer will suffice.
        #     If you need to use a tool, provide a clear explanation of what you're doing.
        #     Always include the tool's name and the arguments you're passing to it.
        #     You can use the tools to get information about the resources.
        #     Available resources: {resource_schemas}
        #     Available resources templates: {resourcesTemplates_schemas}
        #     Available prompts: {prompts_schemas}
        #     You can use the prompts to get information about the resources.
        #     """
        # pprint(f"system_instruction: {system_instruction}\n\n\n")

        # conversation = [{"role": "system", "content": system_instruction}]
        # conversation.append({"role": "user", "content": "Whats the weather in kirkland?"})
        # openAI_tool_schemas = await get_openAI_tool_schema()
        # pprint(f"OpenAI Tool Schema {openAI_tool_schemas}\n\n\n")

        # response = openai_client.chat.completions.create(  
        #     model=MODEL_NAME,
        #     messages=conversation,
        #     max_tokens=800,  
        #     temperature=0.7,  
        #     top_p=0.95,  
        #     frequency_penalty=0,  
        #     presence_penalty=0,
        #     stop=None,  
        #     stream=False,
        #     tools=openAI_tool_schemas,
        #     tool_choice="auto"
        # )

        # print(response.to_json(indent=2))

        # response_message = response.choices[0].message
        # conversation.append(response_message)

        # # Handle function calls
        # if response_message.tool_calls:
        #     for tool_call in response_message.tool_calls:
        #         function_name = tool_call.function.name
        #         function_args = json.loads(tool_call.function.arguments)
        #         print(f"Function call: {function_name}")  
        #         print(f"Function arguments: {function_args}")  
                
        #         # Execute the tool call using the MCP client
        #         tool_result = await client.call_tool(function_name, function_args)
        #         print(f"Tool result: {tool_result}")
                
        #         conversation.append({
        #             "tool_call_id": tool_call.id,
        #             "role": "tool",
        #             "name": function_name,
        #             "content": tool_result,
        #         })
                

        # response = openai_client.chat.completions.create(  
        #     model=MODEL_NAME,
        #     messages=conversation,
        #     max_tokens=800,  
        #     temperature=0.7,  
        #     top_p=0.95,  
        #     frequency_penalty=0,  
        #     presence_penalty=0,
        #     stop=None,  
        #     stream=False,
        #     tools=openAI_tool_schemas,
        #     tool_choice="auto"
        # )

        # print(response.to_json(indent=2))
        # response_message = response.choices[0].message
        # conversation.append(response_message)

        # # Demo: Sampling call: Generate poem
        # openAI_tool_schemas = await get_openAI_tool_schema()
        # system_message = await get_system_message(client)
        # conversation = [{"role": "system", "content": system_message}]
        # conversation.append({"role": "user", "content": "Generate a short poem about the AI."})
        
        # response = openai_client.chat.completions.create(  
        #     model=MODEL_NAME,
        #     messages=conversation,
        #     max_tokens=800,  
        #     temperature=0.7,  
        #     top_p=0.95,  
        #     frequency_penalty=0,  
        #     presence_penalty=0,
        #     stop=None,  
        #     stream=False,
        #     tools=openAI_tool_schemas,
        #     tool_choice="auto"
        # )

        # print(response.to_json(indent=2))
        # # Process the model's response
        # response_message = response.choices[0].message
        # conversation.append(response_message)

        # if response_message.tool_calls:
        #     for tool_call in response_message.tool_calls:
        #         function_name = tool_call.function.name
        #         function_args = json.loads(tool_call.function.arguments)
        #         print(f"Function call: {function_name}")  
        #         print(f"Function arguments: {function_args}")  
                
        #         # Execute the tool call using the MCP client
        #         tool_result = await client.call_tool(function_name, function_args)
        #         print(f"Tool result: {tool_result}")
                
        #         conversation.append({
        #             "tool_call_id": tool_call.id,
        #             "role": "tool",
        #             "name": function_name,
        #             "content": tool_result,
        #         })

        # # Demo: Sampling call: Summarize document
        # openAI_tool_schemas = await get_openAI_tool_schema()
        # system_message = await get_system_message(client)
        # conversation = [{"role": "system", "content": system_message}]
        # conversation.append({"role": "user", "content": "Summarize document of the resource mcp overview"})
        
        # response = openai_client.chat.completions.create(  
        #     model=MODEL_NAME,
        #     messages=conversation,
        #     max_tokens=800,  
        #     temperature=0.7,  
        #     top_p=0.95,  
        #     frequency_penalty=0,
        #     presence_penalty=0,
        #     stop=None,  
        #     stream=False,
        #     tools=openAI_tool_schemas,
        #     tool_choice="auto"
        # )

        # print(response.to_json(indent=2))
        # # Process the model's response
        # response_message = response.choices[0].message
        # conversation.append(response_message)

        # if response_message.tool_calls:
        #     for tool_call in response_message.tool_calls:
        #         function_name = tool_call.function.name
        #         function_args = json.loads(tool_call.function.arguments)
        #         print(f"Function call: {function_name}")  
        #         print(f"Function arguments: {function_args}")  
                
        #         # Execute the tool call using the MCP client
        #         tool_result = await client.call_tool(function_name, function_args)
        #         print(f"Tool result: {tool_result}")
                
        #         conversation.append({
        #             "tool_call_id": tool_call.id,
        #             "role": "tool",
        #             "name": function_name,
        #             "content": tool_result,
        #         })

#         # Demo: Prompt: Initialize a debug session
#         error_message = f"""
#                              Can you help me initialize session to debug the code?
#                              File "/home/stanley/code_samples/main.py", line 2
#     print("Missing colon")
#     ^
# IndentationError: expected an indented block after 'if' statement on line 1
#                              """
        
#         debug_prompt = await client.get_prompt("debug_session_start", {"error_message": error_message})    
#         conversation = [{"role": prompt.role, "content": prompt.content.text} for prompt in debug_prompt]
#         pprint(f"conversation: {conversation}\n\n\n")
        
#         response = openai_client.chat.completions.create(  
#             model=MODEL_NAME,
#             messages=conversation,
#             max_tokens=800,  
#             temperature=0.7,  
#             top_p=0.95,  
#             frequency_penalty=0,
#             presence_penalty=0,
#             stop=None,  
#             stream=False,
#         )

#         print(response.to_json(indent=2))
#         response_message = response.choices[0].message
#         conversation.append(response_message)


    # Connection is closed automatically here
    print(f"Client connected: {client.is_connected()}")

if __name__ == "__main__":
    # Check if the user wants to run in chat mode
    if len(sys.argv) > 1 and sys.argv[1] == "chat":
        asyncio.run(chat_loop())
    else:
        asyncio.run(main())