<!-- DANSWER_METADATA={"link": "https://github.com/onyx-dot-app/onyx/blob/main/README.md"} -->

<a name="readme-top"></a>

<h2 align="center">
<a href="https://www.seclore.com/"> <img width="50%" src="https://astra.seclore.com/logotype.png" /></a>
</h2>



<strong>[Seclore](https://www.seclore.com/)</strong> is the AI Assistant connected to your company's docs, apps, and people.
Seclore provides a Chat interface and plugs into any LLM of your choice. Seclore can be deployed anywhere and for any
scale - on a laptop, on-premise, or to cloud. Since you own the deployment, your user data and chats are fully in your
own control. Seclore is dual Licensed with most of it under MIT license and designed to be modular and easily extensible. The system also comes fully ready
for production usage with user authentication, role management (admin/basic users), chat persistence, and a UI for
configuring AI Assistants.

Seclore also serves as a Enterprise Search across all common workplace tools such as Slack, Google Drive, Confluence, etc.
By combining LLMs and team specific knowledge, Seclore becomes a subject matter expert for the team. Imagine ChatGPT if
it had access to your team's unique knowledge! It enables questions such as "A customer wants feature X, is this already
supported?" or "Where's the pull request for feature Y?"

## 🚀 How to Run This Project

### Prerequisites
- Docker and Docker Compose installed
- Git installed
- At least 8GB RAM available

### Quick Start
1. **Shallow pull the project from main:**
   ```bash
   git clone --depth 1 https://github.com/seclore/seclore-rag-server.git
   cd seclore-rag-server
   ```

2. **Run via Docker Compose:**
   ```bash
   cd deployment/docker_compose/seclore/dev
   docker-compose -f docker-compose.dev.seclore.yml up -d
   ```

3. **Access the application:**
   - **Web UI:** http://localhost:3000
   - **API Server:** http://localhost:8080
   - **Vespa Index:** http://localhost:19071
   - **Model Server:** http://localhost:9001

### Stopping the Services
```bash
docker-compose -f docker-compose.dev.seclore.yml down
```

## 📚 Documentation

- **[Platform Guide](https://secloretechnology.atlassian.net/wiki/spaces/Automation/pages/2300084400/Seclore+AI+Platform+Guide?atlOrigin=eyJpIjoiMTQ5MzJjZDIzNmRkNDBmMGJmNjRmZjgyMjQ4ZTlkYWEiLCJwIjoiYyJ9)** - Comprehensive platform overview and setup
- **[Migration Guide](https://secloretechnology.atlassian.net/wiki/spaces/Automation/pages/2404253887/Migration+Guide+Version+1.3.0.0+to+1.4.0.0?atlOrigin=eyJpIjoiODY2ZjM5NzBmZmI4NGI2NmE2ZTJjNTA3MmU0ZWZhMmQiLCJwIjoiYyJ9)** - Version migration instructions
- **[Deployment Guide](https://secloretechnology.atlassian.net/wiki/spaces/Automation/folder/2404253751?atlOrigin=eyJpIjoiYmI4ZWY0MDFlZmMxNGEwNTkzMzhlOWNkZGE3ZDE0ZTQiLCJwIjoiYyJ9)** - Production deployment instructions
- **[Release Notes](https://secloretechnology.atlassian.net/wiki/spaces/Automation/pages/2404253738/Gen+AI+Release+Notes+-+1.4.0.0?atlOrigin=eyJpIjoiZjY0MWY4OGIxNDhhNDA1NWI3NmY0Y2IyZTg3ZmRiNDAiLCJwIjoiYyJ9)** - Latest release information
- **[User Guides & Prompts](https://secloretechnology.atlassian.net/wiki/spaces/Automation/folder/2298413212?atlOrigin=eyJpIjoiOTEzOTkxZWZhNjFkNGE3Yzk0ZjNjYzkxZGEzNWIwNGEiLCJwIjoiYyJ9)** - Agent-specific documentation

## 💻 Development Workflow

### Prerequisites
- Python 3.9+ installed
- Node.js 18+ installed
- Docker and Docker Compose
- Git

### Getting Started with Development
1. **Pull the latest code:**
   ```bash
   git pull origin main
   ```

2. **Create a feature branch:**
   ```bash
   git checkout -b feature/your-ticket-number
   ```

3. **Make your changes and commit:**
   ```bash
   git add .
   git commit -m "feat: your feature description"
   ```

4. **Push and create PR:**
   ```bash
   git push origin feature/your-ticket-number
   # Create PR to release candidate or required branch
   ```

### Development Tips
- Run tests before committing: `python -m pytest` (backend) or `npm test` (frontend)
- Follow the existing code style and conventions
- Update documentation for any new features
- Ensure Docker services are running for local development

<h3>Usage</h3>

Seclore Web App:

https://github.com/seclore/seclore-rag-server/assets/32520769/563be14c-9304-47b5-bf0a-9049c2b6f410

Or, plug Seclore into your existing Slack workflows (more integrations to come 😁):

https://github.com/seclore/seclore-rag-server/assets/25087905/3e19739b-d178-4371-9a38-011430bdec1b

For more details on the Admin UI to manage connectors and users, check out our
<strong><a href="https://www.youtube.com/watch?v=geNzY1nbCnU">Full Video Demo</a></strong>!

## Deployment

Seclore can easily be run locally (even on a laptop) or deployed on a virtual machine with a single
`docker compose` command. Checkout our [docs](https://docs.seclore.com/quickstart) to learn more.

We also have built-in support for deployment on Kubernetes. Files for that can be found [here](https://github.com/seclore/seclore-rag-server/tree/main/deployment/kubernetes).

## 💃 Main Features

- Chat UI with the ability to select documents to chat with.
- Create custom AI Assistants with different prompts and backing knowledge sets.
- Connect Seclore with LLM of your choice (self-host for a fully airgapped solution).
- Document Search + AI Answers for natural language queries.
- Connectors to all common workplace tools like Google Drive, Confluence, Slack, etc.
- Slack integration to get answers and search results directly in Slack.

## 🚧 Roadmap

- Chat/Prompt sharing with specific teammates and user groups.
- Multimodal model support, chat with images, video etc.
- Choosing between LLMs and parameters during chat session.
- Tool calling and agent configurations options.
- Organizational understanding and ability to locate and suggest experts from your team.

## Other Notable Benefits of Seclore

- User Authentication with document level access management.
- Best in class Hybrid Search across all sources (BM-25 + prefix aware embedding models).
- Admin Dashboard to configure connectors, document-sets, access, etc.
- Custom deep learning models + learn from user feedback.
- Easy deployment and ability to host Seclore anywhere of your choosing.

## 🔌 Connectors

Efficiently pulls the latest changes from:

- Slack
- GitHub
- Google Drive
- Confluence
- Jira
- Zendesk
- Gmail
- Notion
- Gong
- Slab
- Linear
- Productboard
- Guru
- Bookstack
- Document360
- Sharepoint
- Hubspot
- Local Files
- Websites.
- And more ...

## 🏗️ Architecture & Design

For detailed information about Seclore's system architecture, design patterns, and technical implementation:

- **[Architecture Design Document](https://secloretechnology.atlassian.net/wiki/x/EACQk)** - Comprehensive system architecture overview, design decisions, and technical specifications

This document provides insights into:
- System components and their interactions
- Data flow and processing pipelines
- Scalability and performance considerations
- Security architecture and data protection
- Integration patterns and APIs

## 💡 Contributing

Looking to contribute? Please check out the [Contribution Guide](CONTRIBUTING.md) for more details.

## ⭐Star History

[![Star History Chart](https://api.star-history.com/svg?repos=seclore/seclore-rag-server&type=Date)](https://star-history.com/#seclore/seclore-rag-server&Date)
