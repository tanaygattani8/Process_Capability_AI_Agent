from promptflow import tool


import re

def preprocess_markdown(content):
    """
    Pre-process raw markdown content that may be on a single line.
    Adds proper line breaks before markdown elements.
    """
    # Add newlines before headers (## and ###)
    content = re.sub(r'\s*(#{2,3})\s+', r'\n\n\1 ', content)
    
    # Add newlines before list items (- )
    content = re.sub(r'\s+(-\s+\*\*)', r'\n\1', content)
    
    # Add newlines before numbered items (1. 2. etc)
    content = re.sub(r'\s+(\d+\.\s+\*\*)', r'\n\n\1', content)
    
    # Add newlines before blockquotes (>)
    content = re.sub(r'\s+(>)', r'\n\n\1', content)
    
    return content.strip()


def parse_markdown_to_html(content):
    """
    Manually parse the markdown content into structured HTML.
    This handles the specific format of the Tex1.md file.
    """
    # Pre-process to add line breaks
    content = preprocess_markdown(content)
    lines = content.split('\n')
    
    html_parts = []
    in_list = False
    list_depth = 0
    in_ordered_list = False
    
    for line in lines:
        line = line.strip()
        if not line:
            if in_list:
                html_parts.append('</ul>')
                in_list = False
                list_depth = 0
            if in_ordered_list:
                html_parts.append('</ol>')
                in_ordered_list = False
            continue
        
        # Handle H2 headers (##)
        if line.startswith('## '):
            if in_list:
                html_parts.append('</ul>')
                in_list = False
            if in_ordered_list:
                html_parts.append('</ol>')
                in_ordered_list = False
            header_text = line[3:].strip()
            header_text = format_inline(header_text)
            html_parts.append(f'<h2>{header_text}</h2>')
            continue
        
        # Handle H3 headers (###)
        if line.startswith('### '):
            if in_list:
                html_parts.append('</ul>')
                in_list = False
            if in_ordered_list:
                html_parts.append('</ol>')
                in_ordered_list = False
            header_text = line[4:].strip()
            header_text = format_inline(header_text)
            html_parts.append(f'<h3>{header_text}</h3>')
            continue
        
        # Handle numbered list items
        numbered_match = re.match(r'^(\d+)\.\s+(.+)$', line)
        if numbered_match:
            if in_list:
                html_parts.append('</ul>')
                in_list = False
            if not in_ordered_list:
                html_parts.append('<ol>')
                in_ordered_list = True
            item_text = format_inline(numbered_match.group(2))
            html_parts.append(f'<li>{item_text}</li>')
            continue
        
        # Handle unordered list items (-)
        if line.startswith('- '):
            if in_ordered_list:
                html_parts.append('</ol>')
                in_ordered_list = False
            if not in_list:
                html_parts.append('<ul>')
                in_list = True
            item_text = format_inline(line[2:])
            html_parts.append(f'<li>{item_text}</li>')
            continue
        
        # Handle blockquotes
        if line.startswith('>'):
            if in_list:
                html_parts.append('</ul>')
                in_list = False
            if in_ordered_list:
                html_parts.append('</ol>')
                in_ordered_list = False
            quote_text = format_inline(line[1:].strip())
            html_parts.append(f'<blockquote>{quote_text}</blockquote>')
            continue
        
        # Regular paragraph
        if in_list:
            html_parts.append('</ul>')
            in_list = False
        if in_ordered_list:
            html_parts.append('</ol>')
            in_ordered_list = False
        html_parts.append(f'<p>{format_inline(line)}</p>')
    
    # Close any open lists
    if in_list:
        html_parts.append('</ul>')
    if in_ordered_list:
        html_parts.append('</ol>')
    
    return '\n'.join(html_parts)


def format_inline(text):
    """Format inline elements like bold, italic, code, and URLs as images."""
    # Handle URLs - convert to embedded images
    # Match URLs starting with http:// or https://
    text = re.sub(
        r'(https?://[^\s<>"\']+\.(?:png|jpg|jpeg|gif|bmp|webp|svg))',
        r'<img src="\1" alt="Image" class="embedded-image">',
        text,
        flags=re.IGNORECASE
    )
    # Convert any remaining URLs to embedded images (assuming they might be images)
    text = re.sub(
        r'(?<!["\'])(?<!=)(https?://[^\s<>"\']+)(?!["\'])',
        r'<img src="\1" alt="Embedded content" class="embedded-image">',
        text
    )
    # Handle LaTeX inline formulas \( ... \)
    text = re.sub(
        r'\\\((.+?)\\\)',
        r'<span class="math-inline">\\(\1\\)</span>',
        text
    )
    # Handle LaTeX display formulas \[ ... \]
    text = re.sub(
        r'\\\[(.+?)\\\]',
        r'<div class="math-display">\\[\1\\]</div>',
        text
    )
    # Handle LaTeX inline formulas $ ... $ (single dollar)
    text = re.sub(
        r'(?<!\\)\$([^$]+?)\$(?!\$)',
        r'<span class="math-inline">\\(\1\\)</span>',
        text
    )
    # Handle LaTeX display formulas $$ ... $$
    text = re.sub(
        r'\$\$(.+?)\$\$',
        r'<div class="math-display">\\[\1\\]</div>',
        text
    )
    # Handle **bold**
    text = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', text)
    # Handle *italic*
    text = re.sub(r'\*([^*]+)\*', r'<em>\1</em>', text)
    # Handle `code`
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
    # Handle Greek letters (σ)
    text = text.replace('σ', '&sigma;')
    return text



def render_markdown_to_html(markdown_content):
    """
    Reads a Markdown file, converts it to a beautifully formatted HTML document.
    
    Args:
        input_file (str): Path to the input Markdown file.
        output_file (str): Path to save the formatted HTML output.
    """
    try:
       
        # Parse markdown to HTML using custom parser
        html_body = parse_markdown_to_html(markdown_content)

        # Create a complete HTML document with professional CSS styling
        html_document = f"""<!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Process Capability Analysis Report</title>
            <script src="https://polyfill.io/v3/polyfill.min.js?features=es6"></script>
            <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
            <style>
                .math-inline {{
                    display: inline;
                }}
                
                .math-display {{
                    display: block;
                    text-align: center;
                    margin: 15px 0;
                    overflow-x: auto;
                }}
                * {{
                    margin: 0;
                    padding: 0;
                    box-sizing: border-box;
                }}
                
                body {{
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    line-height: 1.8;
                    color: #333;
                    max-width: 900px;
                    margin: 0 auto;
                    padding: 40px 20px;
                    background-color: #f5f5f5;
                }}
                
                .container {{
                    background-color: white;
                    padding: 50px;
                    border-radius: 10px;
                    box-shadow: 0 2px 15px rgba(0,0,0,0.1);
                }}
                
                h2 {{
                    color: #2c3e50;
                    font-size: 1.2em;
                    margin-top: 35px;
                    margin-bottom: 20px;
                    padding-bottom: 10px;
                    border-bottom: 3px solid #3498db;
                }}
                
                h3 {{
                    color: #34495e;
                    font-size: 1em;
                    margin-top: 25px;
                    margin-bottom: 15px;
                }}
                
                h2:first-child {{
                    margin-top: 0;
                }}
                
                ul {{
                    margin-left: 25px;
                    margin-bottom: 15px;
                }}
                
                li {{
                    margin-bottom: 10px;
                    padding-left: 5px;
                }}
                
                ul ul {{
                    margin-top: 10px;
                    margin-bottom: 10px;
                }}
                
                strong {{
                    color: #2c3e50;
                }}
                
                p {{
                    margin-bottom: 15px;
                    text-align: justify;
                }}
                
                blockquote {{
                    background-color: #ecf0f1;
                    border-left: 4px solid #3498db;
                    padding: 15px 20px;
                    margin: 20px 0;
                    font-style: italic;
                    color: #555;
                }}
                
                ol {{
                    margin-left: 25px;
                    margin-bottom: 15px;
                }}
                
                ol li {{
                    margin-bottom: 15px;
                }}
                
                code {{
                    background-color: #f8f8f8;
                    padding: 2px 6px;
                    border-radius: 3px;
                    font-family: 'Consolas', monospace;
                    font-size: 0.9em;
                }}
                
                .embedded-image {{
                    max-width: 100%;
                    height: auto;
                    display: block;
                    margin: 20px auto;
                    border-radius: 8px;
                    box-shadow: 0 2px 10px rgba(0,0,0,0.15);
                }}
                
                .header {{
                    text-align: center;
                    margin-bottom: 40px;
                    padding-bottom: 20px;
                    border-bottom: 2px solid #eee;
                }}
                
                .header h1 {{
                    color: #2c3e50;
                    font-size: 2.2em;
                    margin-bottom: 10px;
                }}
                
                .header .subtitle {{
                    color: #7f8c8d;
                    font-size: 0.6em;
                }}
                
                .footer {{
                    margin-top: 40px;
                    padding-top: 20px;
                    border-top: 2px solid #eee;
                    text-align: center;
                    color: #7f8c8d;
                    font-size: 0.9em;
                }}
                
                @media print {{
                    body {{
                        background-color: white;
                        padding: 0;
                    }}
                    .container {{
                        box-shadow: none;
                        padding: 20px;
                    }}
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Process Capability Analysis</h1>
                    <p class="subtitle">Technical Report</p>
                </div>
                
                {html_body}
                
                <div class="footer">
                    <p>Generated Report | Confidential</p>
                </div>
            </div>
        </body>
        </html>
        """

        return html_document

    except FileNotFoundError:
        print(f"Error: Input file '{input_file}' not found.")
    except Exception as e:
        print(f"An error occurred: {e}")

    return html_document

@tool
def aggregator_output(o_aggregator: str) -> str:
    html_output = render_markdown_to_html(o_aggregator)
    return html_output
    
    #return {
    #    "status": 200,
    #    "headers": { "Content-Type": "text/html" },
    #    "body": html_output
    #    }
