from typing import Any, Dict, Tuple
import os
from pathlib import Path
import httpx
from PIL import Image as PILImage
from io import BytesIO
from mcp.types import PromptMessage
from fastmcp import FastMCP, Context, Image as MCPImage
from fastmcp.prompts.prompt import Message, TextContent
import base64
import logging


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
logging.basicConfig(level=logging.DEBUG)
mcp = FastMCP(name="Tutorial Server")

############################## Tool ##############################
# Constants
NWS_API_BASE = "https://api.weather.gov"
USER_AGENT = "weather-app/1.0"


async def make_nws_request(url: str) -> dict[str, Any] | None:
    """Make a request to the NWS API with proper error handling."""
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/geo+json"
    }
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, timeout=30.0)
            response.raise_for_status()
            return response.json()
        except Exception:
            return None

def format_alert(feature: dict) -> str:
    """Format an alert feature into a readable string."""
    props = feature["properties"]
    return f"""
Event: {props.get('event', 'Unknown')}
Area: {props.get('areaDesc', 'Unknown')}
Severity: {props.get('severity', 'Unknown')}
Description: {props.get('description', 'No description available')}
Instructions: {props.get('instruction', 'No specific instructions provided')}
"""

@mcp.tool()
async def get_alerts(state: str) -> str:
    """Get weather alerts for a US state.

    Args:
        state: Two-letter US state code (e.g. CA, NY)
    """
    url = f"{NWS_API_BASE}/alerts/active/area/{state}"
    data = await make_nws_request(url)

    if not data or "features" not in data:
        return "Unable to fetch alerts or no alerts found."

    if not data["features"]:
        return "No active alerts for this state."

    alerts = [format_alert(feature) for feature in data["features"]]
    return "\n---\n".join(alerts)

@mcp.tool()
async def get_forecast(latitude: float, longitude: float, ctx: Context) -> str:
    """Get weather forecast for a location.

    Args:
        latitude: Latitude of the location
        longitude: Longitude of the location
    """
    # roots = await ctx.list_roots()
    # await ctx.info(f"{bcolors.HEADER}{roots}")
    await ctx.info(f"{bcolors.OKGREEN}Info Message: Processing coordinates: {latitude}, {longitude}")
    # await ctx.report_progress(0, 100)
    # First get the forecast grid endpoint
    points_url = f"{NWS_API_BASE}/points/{latitude},{longitude}"
    points_data = await make_nws_request(points_url)

    if not points_data:
        return "Unable to fetch forecast data for this location."

    # Get the forecast URL from the points response
    forecast_url = points_data["properties"]["forecast"]
    forecast_data = await make_nws_request(forecast_url)

    if not forecast_data:
        return "Unable to fetch detailed forecast."

    await ctx.report_progress(50, 100)
    # Format the periods into a readable forecast
    periods = forecast_data["properties"]["periods"]
    forecasts = []
    for period in periods[:5]:  # Only show next 5 periods
        forecast = f"""
                    {period['name']}:
                    Temperature: {period['temperature']}°{period['temperatureUnit']}
                    Wind: {period['windSpeed']} {period['windDirection']}
                    Forecast: {period['detailedForecast']}
                    """
        forecasts.append(forecast)
    await ctx.report_progress(100, 100)
    return "\n---\n".join(forecasts)

@mcp.tool()
def create_thumbnail(image_path: str) -> Tuple[bytes, str]:
    """
    Create a 10×10 PNG thumbnail from the input image.
    
    This function takes a path to an existing image file, resizes it to a thumbnail
    while preserving the aspect ratio, and returns the image data in base64 encoding.
    
    Args:
        image_path: Full path to the source image file to be thumbnailed
        
    Returns:
        Tuple[bytes, str]: A tuple containing:
          - The base64 encoded image data in bytes(can be used in HTML/CSS)
          - The MIME type of the image ("image/png")
    """
    img = PILImage.open(image_path)
    img.thumbnail((10, 10))    
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    mime_type = f"image/png"
    
    # Convert bytes to string for proper JSON serialization
    encoded_bytes = base64.b64encode(buffer.getvalue())
    return encoded_bytes, mime_type

@mcp.tool()
def save_thumbnail(image_path: str, image_bytes_base64: bytes) -> str:
    """
    Save the thumbnail locally given base64-encoded PNG data to the path.
    
    This function saves a thumbnail image from base64-encoded data to the specified path
    on the filesystem. It's typically used in conjunction with create_thumbnail to
    persist thumbnails that have been generated.
    
    Args:
        image_path: Full path where the thumbnail will be saved (including filename and extension)
        image_bytes_base64: Base64-encoded image data (usually from create_thumbnail)
        
    Returns:
        str: A confirmation message indicating where the thumbnail was saved
    """
    try:
        # Ensure directory exists
        output_dir = os.path.dirname(image_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        # Decode the base64 data first
        decoded_bytes = base64.b64decode(image_bytes_base64)
        
        # Load from decoded bytes
        with BytesIO(decoded_bytes) as buffer:
            img = PILImage.open(buffer)
            # Write thumbnail back to disk
            output_path = image_path
            img.save(output_path, format="PNG")
            return f"Saved thumbnail to {output_path}"
    except base64.binascii.Error as e:
        return f"Base64 decoding error: {str(e)}"
    except IOError as e:
        return f"Error saving image: {str(e)}"
    except Exception as e:
        return f"Unexpected error processing thumbnail: {str(e)}"

# LLM Sampling
# Sampling is an MCP feature that allows a server to request a completion from the client LLM, enabling sophisticated use cases while maintaining security and privacy on the server.
# This pattern is powerful because:
# The server can delegate text generation to the client LLM
# The server remains focused on business logic and data handling
# The client maintains control over which LLM is used and how requests are handled
# No sensitive data needs to be sent to external APIs
@mcp.tool()
async def generate_poem(topic: str, context: Context) -> str:
    """Generate a short poem about the given topic."""
    request_id = context.request_id
    await context.info(f"[{request_id}] Starting processing for {topic}")
    # The server requests a completion from the client LLM
    response = await context.sample(
        messages=f"Write a short poem about {topic}",
        system_prompt="You are a talented poet who writes concise, evocative verses.",
        temperature=0.7,
        max_tokens=300
    )
    return response.text

@mcp.tool()
async def summarize_document(document_uri: str, context: Context) -> str:
    """Summarize a document using client-side LLM capabilities."""
    # First read the document as a resource
    doc_resource = await context.read_resource(document_uri)
    doc_content = doc_resource[0].content  # Assuming single text content
    
    # Then ask the client LLM to summarize it
    response = await context.sample(
        f"Summarize the following document:\n\n{doc_content}",
        system_prompt="You are an expert summarizer. Create a concise summary."
    )
    return response.text

############################## Resource ##############################
ANIMALS = {
    "lion": {
        "name": "Lion",
        "scientific_name": "Panthera leo",
        "type": "Mammal",
        "habitat": "Savanna, grassland",
        "diet": "Carnivore",
        "lifespan": "10-14 years in the wild",
        "description": "Lions are the second largest big cat species after tigers. They are known for their distinctive manes (in males) and social behavior, living in groups called prides."
    },
    "tiger": {
        "name": "Tiger",
        "scientific_name": "Panthera tigris",
        "type": "Mammal",
        "habitat": "Forest, grassland, swamp",
        "diet": "Carnivore",
        "lifespan": "10-15 years in the wild",
        "description": "Tigers are the largest cat species with distinctive orange fur with black stripes. They are solitary hunters and excellent swimmers."
    },
    "cat": {
        "name": "Domestic Cat",
        "scientific_name": "Felis catus",
        "type": "Mammal",
        "habitat": "Various, often domesticated",
        "diet": "Carnivore",
        "lifespan": "12-18 years",
        "description": "Domestic cats are small, carnivorous mammals that have been living alongside humans for thousands of years. They are known for their agility, independent nature, and grooming behavior."
    },
    "dog": {
        "name": "Domestic Dog",
        "scientific_name": "Canis familiaris",
        "type": "Mammal",
        "habitat": "Various, domesticated",
        "diet": "Omnivore",
        "lifespan": "10-13 years on average",
        "description": "Dogs were the first domesticated animal and have evolved alongside humans for over 15,000 years. They come in hundreds of breeds with diverse appearances and temperaments."
    },
    "bird": {
        "name": "Bird",
        "scientific_name": "Class Aves",
        "type": "Vertebrate",
        "habitat": "Diverse - worldwide",
        "diet": "Varies by species",
        "lifespan": "Varies by species",
        "description": "Birds are feathered, winged animals that lay eggs. They have lightweight, hollow bones and are the only living descendants of dinosaurs."
    },
    "horse": {
        "name": "Horse",
        "scientific_name": "Equus ferus caballus",
        "type": "Mammal",
        "habitat": "Grasslands, plains",
        "diet": "Herbivore",
        "lifespan": "25-30 years",
        "description": "Horses are large mammals that have been domesticated for thousands of years. They are known for their strength, speed, and their historical importance in transportation, agriculture, and warfare."
    }
}

# Register a static greeting
@mcp.resource("greeting://welcome")
def get_greeting_message() -> str:
    """Static greeting message"""
    return "Welcome to the MCP Tutorial Server!"

# Register a static mcp resource
@mcp.resource("mcp://overview", description="Overview of the Model Context Protocol")
def get_greeting_message() -> str:
    return """"Model Context Protocol
The Model Context Protocol is an open standard that enables developers to build secure, two-way connections between their data sources and AI-powered tools. The architecture is straightforward: developers can either expose their data through MCP servers or build AI applications (MCP clients) that connect to these servers.

Today, we're introducing three major components of the Model Context Protocol for developers:

The Model Context Protocol specification and SDKs
Local MCP server support in the Claude Desktop apps
An open-source repository of MCP servers
Claude 3.5 Sonnet is adept at quickly building MCP server implementations, making it easy for organizations and individuals to rapidly connect their most important datasets with a range of AI-powered tools. To help developers start exploring, we’re sharing pre-built MCP servers for popular enterprise systems like Google Drive, Slack, GitHub, Git, Postgres, and Puppeteer.

Early adopters like Block and Apollo have integrated MCP into their systems, while development tools companies including Zed, Replit, Codeium, and Sourcegraph are working with MCP to enhance their platforms—enabling AI agents to better retrieve relevant information to further understand the context around a coding task and produce more nuanced and functional code with fewer attempts.

"At Block, open source is more than a development model—it’s the foundation of our work and a commitment to creating technology that drives meaningful change and serves as a public good for all,” said Dhanji R. Prasanna, Chief Technology Officer at Block. “Open technologies like the Model Context Protocol are the bridges that connect AI to real-world applications, ensuring innovation is accessible, transparent, and rooted in collaboration. We are excited to partner on a protocol and use it to build agentic systems, which remove the burden of the mechanical so people can focus on the creative.”

Instead of maintaining separate connectors for each data source, developers can now build against a standard protocol. As the ecosystem matures, AI systems will maintain context as they move between different tools and datasets, replacing today's fragmented integrations with a more sustainable architecture.

Getting started
Developers can start building and testing MCP connectors today. All Claude.ai plans support connecting MCP servers to the Claude Desktop app.

Claude for Work customers can begin testing MCP servers locally, connecting Claude to internal systems and datasets. We'll soon provide developer toolkits for deploying remote production MCP servers that can serve your entire Claude for Work organization."""

# Register system status with context
@mcp.resource("system://status")
async def get_system_status() -> dict:
    """Report the current system status."""
    # https://github.com/modelcontextprotocol/python-sdk/issues/244
    ctx = mcp.get_context()
    await ctx.info("Checking system status...")
    # Perform checks
    await ctx.report_progress(1, 1) # Report completion
    return {"status": "OK", "load": 0.5, "client": ctx.client_id}


# Register a dynamic resource template for animals
@mcp.resource("animal://{animal_name}")
def get_animal_info(animal_name: str) -> Dict[str, Any]:
    """Dynamic animal information resource"""
    if animal_name in ANIMALS:
        return ANIMALS[animal_name]
    raise ValueError(f"Unknown animal: {animal_name}")

# Register a list resource to show all available animals
@mcp.resource("animals://list")
def list_animals() -> Dict[str, str]:
    """List of all available animals"""
    return {name: animal["name"] for name, animal in ANIMALS.items()}

# Register a list resource to show all available animals images
@mcp.resource("image://list")
def list_animals() -> Dict[str, str]:
    """List of all available animals images"""
    return {"dog": "dog.png"}

# Register a dynamic resource template for images
@mcp.resource("image://{image_name}")
def get_image(image_name: str) -> Tuple[str, str]:
    """Dynamic image file reader resource, will return base64 encoded image data and mime type.
    Args:
        image_name: The name of the image file (e.g. dog.png)
    Returns:
        Tuple[str, str]: A tuple containing the base64 encoded image data and its MIME type.
    
    Examples:
    - if you want to get dog.png, use image://dog.png to access resource
    """
    # For safety, restrict to a specific directory
    base_dir = Path(__file__).parent / "images"
    
    # Ensure the base directory exists
    os.makedirs(base_dir, exist_ok=True)
    
    # Build the full path and ensure it's within the allowed directory
    full_path = (base_dir / image_name).resolve()
    if not str(full_path).startswith(str(base_dir.resolve())):
        raise ValueError(f"Access denied: {image_name}")
    
    # Check if the file exists
    if not full_path.exists():
        raise ValueError(f"Image not found: {image_name}")
    
    # Determine MIME type from file extension
    extension = os.path.splitext(image_name)[1][1:].lower()  # Get extension without dot
    mime_type = f"image/{extension}"
    
    # Read the image file as binary
    with open(full_path, 'rb') as f:
        encoded_string = base64.b64encode(f.read())
    
    # Return the image data with the appropriate MIME type
    return encoded_string, mime_type

############################## Prompt ##############################
@mcp.prompt()
def debug_session_start(error_message: str) -> list[PromptMessage]:
    """Initiates a debugging help session."""
    return [
        PromptMessage(role="user", content=TextContent(type="text", text=f"I encountered an error:\n{error_message}, please help me to debug it.")),
        PromptMessage(role="assistant", content=TextContent(type="text", text="Okay, I can help with that. Let me look into the error message you provided and list what's the possible way to fix it."))
    ]

if __name__ == "__main__":
    # This code only runs when the file is executed directly
    
    # Local STDIO
    # mcp.run()

    # SSE
    mcp.run(transport="sse", host="127.0.0.1", port=9000)