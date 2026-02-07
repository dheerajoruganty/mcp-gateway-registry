# Agent Skills Operational Guide

This guide covers registering, managing, and using Agent Skills in MCP Gateway Registry.

## Overview

Agent Skills are reusable instruction sets that enhance AI coding assistants with specialized workflows and behaviors. Skills are defined in SKILL.md files hosted on GitHub, GitLab, or Bitbucket, and registered in the MCP Gateway Registry for discovery and access control.

## Quick Start

### Prerequisites

- MCP Gateway Registry instance running
- Authenticated user account
- SKILL.md file hosted on GitHub, GitLab, or Bitbucket

### Step 1: Create a SKILL.md File

Create a SKILL.md file in your repository following the [agentskills.io](https://agentskills.io) specification:

```markdown
---
name: pdf-processing
description: Convert and manipulate PDF documents using various tools
---

# PDF Processing Skill

This skill helps you work with PDF documents including conversion, extraction, and manipulation.

## When to Use This Skill

- Converting documents to PDF format
- Extracting text or images from PDFs
- Merging or splitting PDF files
- Adding watermarks or annotations

## Workflow

1. Identify the PDF operation needed
2. Check for required tools (pdftk, poppler-utils)
3. Execute the appropriate command
4. Verify the output

## Examples

### Convert HTML to PDF
```bash
wkhtmltopdf input.html output.pdf
```

### Extract text from PDF
```bash
pdftotext document.pdf output.txt
```
```

### Step 2: Register the Skill

**Using the UI:**

1. Navigate to the Skills section in the dashboard
2. Click "Register Skill"
3. Enter the SKILL.md URL (e.g., `https://github.com/org/repo/blob/main/skills/pdf-processing/SKILL.md`)
4. Fill in additional details:
   - Name: Auto-populated from SKILL.md or enter manually
   - Description: Brief description of the skill
   - Visibility: Public, Private, or Group
   - Tags: Add relevant tags for discovery
5. Click "Register"

**Using the API:**

```bash
curl -X POST https://your-registry.com/api/skills \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{
    "name": "pdf-processing",
    "description": "Convert and manipulate PDF documents",
    "skill_md_url": "https://github.com/org/repo/blob/main/skills/pdf-processing/SKILL.md",
    "visibility": "public",
    "tags": ["pdf", "documents", "conversion"]
  }'
```

### Step 3: Verify Registration

Check that the skill is registered and healthy:

```bash
# Get skill details
curl https://your-registry.com/api/skills/pdf-processing \
  -H "Authorization: Bearer <token>"

# Check skill health
curl https://your-registry.com/api/skills/pdf-processing/health \
  -H "Authorization: Bearer <token>"
```

## Managing Skills

### List All Skills

**UI:** Navigate to the Skills section in the dashboard.

**API:**
```bash
# List all enabled skills
curl https://your-registry.com/api/skills \
  -H "Authorization: Bearer <token>"

# Include disabled skills
curl "https://your-registry.com/api/skills?include_disabled=true" \
  -H "Authorization: Bearer <token>"

# Filter by tag
curl "https://your-registry.com/api/skills?tag=pdf" \
  -H "Authorization: Bearer <token>"
```

### Update a Skill

**UI:** Click the edit (pencil) icon on a skill card.

**API:**
```bash
curl -X PUT https://your-registry.com/api/skills/pdf-processing \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{
    "description": "Updated description",
    "tags": ["pdf", "documents", "conversion", "utilities"]
  }'
```

### Enable/Disable Skills

**UI:** Use the toggle switch on the skill card.

**API:**
```bash
# Disable a skill
curl -X PUT https://your-registry.com/api/skills/pdf-processing/disable \
  -H "Authorization: Bearer <token>"

# Enable a skill
curl -X PUT https://your-registry.com/api/skills/pdf-processing/enable \
  -H "Authorization: Bearer <token>"
```

### Delete a Skill

**UI:** Click the delete (trash) icon on a skill card.

**API:**
```bash
curl -X DELETE https://your-registry.com/api/skills/pdf-processing \
  -H "Authorization: Bearer <token>"
```

## Health Monitoring

### Check Skill Health

The registry verifies that SKILL.md files are accessible:

**UI:** Click the refresh icon on a skill card to check health.

**API:**
```bash
curl https://your-registry.com/api/skills/pdf-processing/health \
  -H "Authorization: Bearer <token>"
```

Response:
```json
{
  "healthy": true,
  "status_code": 200,
  "checked_at": "2025-02-07T15:30:00Z"
}
```

### Health Status Indicators

| Status | Meaning |
|--------|---------|
| Healthy (green) | SKILL.md is accessible |
| Unhealthy (red) | SKILL.md fetch failed |
| Unknown (yellow) | Not yet checked |

## Rating Skills

### Submit a Rating

**UI:** Click the star rating widget on a skill card.

**API:**
```bash
curl -X POST https://your-registry.com/api/skills/pdf-processing/rate \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"rating": 5}'
```

### View Ratings

**UI:** Rating is displayed on the skill card.

**API:**
```bash
curl https://your-registry.com/api/skills/pdf-processing/rating \
  -H "Authorization: Bearer <token>"
```

Response:
```json
{
  "num_stars": 4.5,
  "rating_details": [
    {"user": "alice", "rating": 5},
    {"user": "bob", "rating": 4}
  ]
}
```

## Viewing Skill Content

### View SKILL.md Content

**UI:** Click the info (i) icon on a skill card to open the content modal.

The modal displays:
- YAML frontmatter in a table format
- Formatted markdown content
- Links to GitHub source
- Copy and download buttons

**API:**
```bash
curl https://your-registry.com/api/skills/pdf-processing/content \
  -H "Authorization: Bearer <token>"
```

Response:
```json
{
  "content": "---\nname: pdf-processing\n...",
  "url": "https://raw.githubusercontent.com/org/repo/main/skills/pdf-processing/SKILL.md"
}
```

## Tool Validation

Skills can reference required MCP server tools. Validate tool availability:

**UI:** Click the wrench icon on a skill card.

**API:**
```bash
curl https://your-registry.com/api/skills/pdf-processing/tools \
  -H "Authorization: Bearer <token>"
```

Response:
```json
{
  "all_available": true,
  "tool_results": [
    {
      "tool_name": "Bash",
      "server_path": "/servers/claude-tools",
      "available": true
    }
  ],
  "missing_tools": []
}
```

## Access Control

### Visibility Levels

| Level | Description |
|-------|-------------|
| Public | Visible to all authenticated users |
| Private | Visible only to the owner |
| Group | Visible to specified groups |

### Set Visibility

```bash
# Make skill private
curl -X PUT https://your-registry.com/api/skills/pdf-processing \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"visibility": "private"}'

# Make skill visible to specific groups
curl -X PUT https://your-registry.com/api/skills/pdf-processing \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{
    "visibility": "group",
    "allowed_groups": ["engineering", "devops"]
  }'
```

## Search and Discovery

### Search Skills

**UI:** Use the search bar in the Skills section.

**API:**
```bash
# Search by keyword
curl "https://your-registry.com/api/skills/search?q=pdf" \
  -H "Authorization: Bearer <token>"

# Filter by multiple criteria
curl "https://your-registry.com/api/skills/search?q=document&tags=pdf,conversion" \
  -H "Authorization: Bearer <token>"
```

## Integration with AI Assistants

### Claude Code Integration

Skills can be loaded into Claude Code using slash commands:

```
/skill pdf-processing
```

Or via the Claude Code configuration:

```json
{
  "skills": [
    "https://your-registry.com/api/skills/pdf-processing"
  ]
}
```

### Cursor Integration

Add skills to your Cursor configuration:

```json
{
  "ai.skills": [
    "https://your-registry.com/api/skills/pdf-processing/content"
  ]
}
```

## Troubleshooting

### Skill Registration Fails

1. **Invalid URL**: Ensure the URL points to a valid SKILL.md file
2. **Name conflict**: Skill names must be unique
3. **Invalid name format**: Names must be lowercase alphanumeric with hyphens

### Skill Shows as Unhealthy

1. **Check URL**: Verify the SKILL.md file is accessible in a browser
2. **Repository access**: Ensure the repository is public or accessible
3. **Raw URL**: The registry uses raw URLs; verify raw content is accessible

### Rating Not Saved

1. **Authentication**: Ensure you're authenticated
2. **Valid range**: Ratings must be between 1 and 5
3. **Refresh**: Try refreshing the page after rating

### Content Not Loading

1. **CORS**: The registry proxies content to avoid CORS issues
2. **Health check**: Verify the skill is healthy first
3. **Network**: Check network connectivity to the source

## Best Practices

### Skill Naming

- Use lowercase letters and hyphens only
- Choose descriptive, specific names
- Avoid generic names like "helper" or "utils"

### SKILL.md Content

- Include clear trigger conditions
- Provide step-by-step workflows
- Add practical examples
- Document required tools

### Tagging

- Use consistent tag conventions
- Include category tags (e.g., "documents", "automation")
- Add technology tags (e.g., "pdf", "python")

### Visibility

- Start with private for testing
- Use group visibility for team-specific skills
- Make public for community sharing

## API Reference

See [API Reference](api-reference.md) for complete endpoint documentation.

## Related Documentation

- [Agent Skills Architecture](design/agent-skills-architecture.md)
- [Authentication](auth.md)
- [Federation](federation.md)
