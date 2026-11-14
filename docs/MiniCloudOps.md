# **MiniCloudOps: Distributed Infrastructure Monitoring Platform**

This proposal describes MiniCloudOps, a lightweight monitoring platform where developers register applications, track their health and resource use, and manage the resulting incidents from one dashboard. It runs as four REST microservices in Docker, runs locally with Docker Compose, and is tested and built by a GitHub Actions pipeline.

| Item | Detail |
| :---- | :---- |
| Project type | DevOps, microservices application |
| Approach | Local-first, Docker-based deployment |
| Version | 1.0 |
| Status | Proposed |

## **1\. Overview**

### **1.1 Purpose**

Modern applications are spread across servers, containers and services, which makes failures hard to spot and trace. MiniCloudOps gives one place to register applications, monitor their health, detect abnormal conditions, manage incidents and view it all on a dashboard.

Version 1 monitors Docker containers and HTTP applications in a local environment. The architecture leaves room to monitor remote machines later.

### **1.2 Problem**

Developers and small teams need monitoring without enterprise pricing or heavy setup. The gaps MiniCloudOps closes:

* No central view of application health.  
* Downtime goes unnoticed.  
* Little visibility into CPU, memory and resource use.  
* Errors are hard to trace across services.  
* No central incident history.  
* Slow response to failures.

### **1.3 Objectives**

1. Build a microservices-based infrastructure monitoring platform.  
2. Let users register and manage monitored applications.  
3. Collect application health and infrastructure metrics.  
4. Detect failures and abnormal conditions.  
5. Generate and manage incidents automatically.  
6. Provide centralized dashboards.  
7. Implement centralized logging and metrics monitoring.  
8. Containerize every service with Docker.  
9. Set up an automated CI/CD pipeline.  
10. Run the complete platform on localhost with Docker Compose.

### **1.4 Target users**

Software developers, DevOps engineers, system administrators, small development teams, and students learning infrastructure monitoring.

### **1.5 Scope**

**Version 1 (in scope)**

* Monitor HTTP applications and Docker containers.  
* Collect CPU and memory metrics.  
* Check application availability and detect failures.  
* Create and manage incidents.  
* Display monitoring information and visualize metrics.  
* Centralized logging.  
* Docker-based deployment and CI/CD automation.

**Future improvements (out of scope)**

* Kubernetes cluster monitoring.  
* Multi-cloud infrastructure management.  
* Advanced distributed tracing.  
* AI-based anomaly detection.  
* Automatic infrastructure scaling.  
* Complex user access management.  
* Mobile application.  
* Advanced alert delivery integrations.

## **2\. System architecture**

### **2.1 Overview**

MiniCloudOps divides its work among four custom microservices. Each has its own responsibility, API and database, and they communicate over REST. Around them sit a React frontend, an API gateway and the observability tools.

Prometheus, cAdvisor, Node Exporter, Loki and Grafana are supporting infrastructure, not business microservices.

![system architecture · 4 services, 4 databases, observability stack][image1]

system architecture · 4 services, 4 databases, observability stack

The four highlighted boxes are the custom microservices. The gateway fronts the Target, Monitoring and Incident services, and the Incident Service calls the Notification Service. One PostgreSQL container holds the four databases.

### **2.2 Services at a glance**

| Service | Purpose | Database | Example tables |
| :---- | :---- | :---- | :---- |
| Target Management | Manage applications registered for monitoring | target\_db | targets, target\_configurations |
| Monitoring | Collect data and evaluate target health | monitoring\_db | health\_checks, metric\_snapshots, monitoring\_configurations |
| Incident Management | Detect, create and manage incidents | incident\_db | incidents, incident\_events |
| Notification | Create and track notifications | notification\_db | notifications, notification\_templates |

### **2.3 Service responsibilities**

#### **Target Management Service**

* Register, update and remove monitoring targets.  
* Store target configurations and status metadata.  
* Provide target information to the Monitoring Service.

Example target:

{  
  "name": "Example API",  
  "target\_url": "http\://app-server:8000/health",  
  "type": "http",  
  "check\_interval": 30,  
  "enabled": true  
}

#### **Monitoring Service**

* Retrieve registered targets.  
* Run periodic HTTP health checks and measure response time.  
* Query Prometheus for infrastructure metrics.  
* Detect downtime and evaluate monitoring thresholds.  
* Report results to the Incident Management Service.

Example health result:

{  
  "target\_id": "target-001",  
  "status": "DOWN",  
  "response\_time\_ms": null,  
  "checked\_at": "2026-11-14T10:00:00Z"  
}

#### **Incident Management Service**

* Receive monitoring events and create incidents when failures are detected.  
* Track incident severity, status and history.  
* Detect recovery.  
* Notify the Notification Service when an incident is created or resolved.

Example incident:

{  
  "id": "INC-001",  
  "target\_id": "target-001",  
  "title": "Application unavailable",  
  "severity": "CRITICAL",  
  "status": "OPEN",  
  "description": "HTTP health check failed"  
}

#### **Notification Service**

* Receive incident notifications and generate messages.  
* Store notification history and track delivery status.  
* Prevent unnecessary duplicate notifications.

In Version 1, notifications appear on the MiniCloudOps dashboard. Email is an optional extension.

## **3\. Service communication**

### **3.1 Approach**

Services communicate over REST using HTTP and JSON. Version 1 uses synchronous calls to keep the architecture manageable.

### **3.2 Main workflow**

1. The Target Management Service registers an application.  
2. The Monitoring Service retrieves its configuration.  
3. The Monitoring Service checks the application's health.  
4. The Monitoring Service sends the result to the Incident Management Service.  
5. The Incident Management Service creates or updates an incident when the check fails.  
6. The Incident Management Service calls the Notification Service.  
7. The Notification Service stores a notification.  
8. The frontend displays the updated status.

A healthy result skips steps 5 to 7 and goes straight to the dashboard.

### **3.3 Failure handling**

A failure in one component must not take down the whole platform.

| Failure | Expected behavior |
| :---- | :---- |
| Monitored application is down | Monitoring Service records a failed health check |
| Incident Service is temporarily unavailable | Monitoring Service retries submitting the result |
| Notification Service is unavailable | The incident is still saved successfully |
| Prometheus is unavailable | Infrastructure metrics are reported as temporarily unavailable, never as zero |

Retries should use a limited number of attempts with exponential backoff. A future improvement can add RabbitMQ for asynchronous event delivery.

## **4\. Database architecture**

### **4.1 Ownership**

Each microservice owns its data. The first implementation can run one PostgreSQL container holding four separate databases. Each service gets its own credentials and must never query another service's database.

| Microservice | Database |
| :---- | :---- |
| Target Service | target\_db |
| Monitoring Service | monitoring\_db |
| Incident Service | incident\_db |
| Notification Service | notification\_db |

### **4.2 Data relationships**

Services refer to each other's entities by identifier, not by shared tables:

* Monitoring Service stores target\_id.  
* Incident Service stores target\_id.  
* Notification Service stores incident\_id.

When a service needs more information, it asks the owning service through its REST API.

## **5\. API design**

Every service exposes a REST API. These are the proposed Version 1 endpoints.

### **5.1 Target Management API**

Base path: /api/v1/targets

| Method | Endpoint | Description |
| :---- | :---- | :---- |
| POST | / | Register a target |
| GET | / | List targets |
| GET | /{id} | Get target details |
| PUT | /{id} | Update a target |
| DELETE | /{id} | Delete a target |
| PATCH | /{id}/enable | Enable a target |
| PATCH | /{id}/disable | Disable a target |

### **5.2 Monitoring API**

Base path: /api/v1/monitoring

| Method | Endpoint | Description |
| :---- | :---- | :---- |
| GET | /health | Service health |
| GET | /targets/{id}/status | Target health status |
| GET | /targets/{id}/history | Health-check history |
| GET | /metrics | Expose Prometheus metrics |
| POST | /check/{id} | Trigger a manual health check |

### **5.3 Incident Management API**

Base path: /api/v1/incidents

| Method | Endpoint | Description |
| :---- | :---- | :---- |
| GET | / | List incidents |
| GET | /{id} | Get incident details |
| POST | / | Create an incident |
| PATCH | /{id}/status | Update incident status |
| GET | /{id}/history | Get incident history |

### **5.4 Notification API**

Base path: /api/v1/notifications

| Method | Endpoint | Description |
| :---- | :---- | :---- |
| GET | / | List notifications |
| GET | /{id} | Get a notification |
| POST | / | Create a notification |
| PATCH | /{id}/read | Mark as read |

### **5.5 API standards**

All services follow the same conventions:

* JSON request and response formats.  
* Appropriate HTTP status codes.  
* Input validation.  
* Standardized error responses.  
* API versioning.  
* Request correlation IDs.  
* OpenAPI documentation.

## **6\. Technology stack**

| Layer | Technology | Purpose |
| :---- | :---- | :---- |
| Frontend | React | Monitoring dashboard |
| Backend | Python FastAPI | Microservices |
| Service communication | REST / HTTP | Calls between services |
| Database | PostgreSQL | Persistent service data |
| Metrics | Prometheus | Metrics collection |
| Container metrics | cAdvisor | Docker monitoring |
| Host metrics | Node Exporter | Host monitoring |
| Visualization | Grafana | Metrics dashboards |
| Logging | Loki | Centralized logs |
| Log collection | Grafana Alloy | Log forwarding |
| Containerization | Docker | Application packaging |
| Local orchestration | Docker Compose | Container management |
| CI/CD | GitHub Actions | Automated workflow |
| Container registry | GitHub Container Registry (GHCR) | Image publishing |
| Deployment | Docker Compose on localhost | Application deployment |
| API testing | Postman / curl | API verification |
| Automated testing | Pytest | Backend testing |

### **Why these choices**

* **FastAPI** is lightweight and generates API documentation automatically.  
* **PostgreSQL** provides reliable relational storage.  
* **Prometheus** collects and stores time-series metrics.  
* **Grafana** visualizes metrics and logs.  
* **Loki** centralizes application logs.  
* **Docker Compose** runs the whole stack locally.  
* **GitHub Actions** automates testing and image publishing.  
* **Grafana Alloy** is the log collector. Promtail has reached end of life and should not be used in a new implementation.

## **7\. Infrastructure monitoring**

### **7.1 What is monitored**

| Category | Capabilities |
| :---- | :---- |
| Application | Availability, HTTP response status, response time, request failures, health-check history |
| Infrastructure | CPU utilization, memory utilization, container status, container resource usage, host resource consumption |

### **7.2 Metrics collection**

Prometheus scrapes three sources: the Monitoring Service /metrics endpoint, cAdvisor and Node Exporter. The Monitoring Service queries Prometheus whenever it needs infrastructure metrics.

Custom application metrics are implemented with the Prometheus Python client:

miniops\_health\_check\_total  
miniops\_health\_check\_failures\_total  
miniops\_http\_response\_time\_seconds  
miniops\_active\_targets  
miniops\_open\_incidents

### **7.3 Alert rules**

| Condition | Severity | Suggested threshold |
| :---- | :---- | :---- |
| Application unavailable | Critical | HTTP health check fails three consecutive times |
| High CPU usage | Warning | Above 80% for 1 minute |
| High memory usage | Warning | Above 85% for 1 minute |
| Excessive response time | Warning | Above 2 seconds for repeated checks |
| Application recovered | Recovery | Target returns to UP |

These are configurable demonstration thresholds, not production recommendations.

## **8\. Centralized logging**

### **8.1 Architecture**

Every custom microservice writes structured JSON logs. Grafana Alloy collects the container logs and forwards them to Loki, and Grafana provides one interface for searching and investigating them.

### **8.2 Example log entry**

{  
  "timestamp": "2026-11-14T10:00:00Z",  
  "level": "ERROR",  
  "service": "monitoring-service",  
  "correlation\_id": "req-12345",  
  "message": "Health check failed",  
  "target\_id": "target-001",  
  "status\_code": 503  
}

### **8.3 Requirements**

Each service logs:

* Application startup and shutdown.  
* Incoming and failed requests.  
* Database errors.  
* Service-to-service communication.  
* Monitoring failures.  
* Incident creation.  
* Notification delivery.

Passwords, API tokens and database credentials must never appear in logs.

### **8.4 Demonstration**

1. Stop one monitored application.  
2. Wait for the health check to fail.  
3. Open Grafana Explore.  
4. Search for the Monitoring Service logs.  
5. Filter by correlation ID.  
6. Follow the failure through the Incident and Notification Services.

This shows how centralized logging helps investigate failures across distributed services.

## **9\. Docker and containerization**

### **9.1 Requirements**

Every custom microservice has its own Dockerfile. A Docker Compose configuration runs the entire application locally.

### **9.2 Docker Compose services**

Compose defines the four custom microservices, the frontend, the API gateway, PostgreSQL, Prometheus, Grafana, Loki, Grafana Alloy, cAdvisor and Node Exporter. Databases and monitoring data use persistent volumes. Docker networks separate internal service traffic from publicly reachable endpoints.

### **9.3 Repository structure**

miniops/  
├── frontend/  
│   ├── src/  
│   ├── Dockerfile  
│   └── package.json  
├── services/  
│   ├── target-service/  
│   ├── monitoring-service/  
│   ├── incident-service/  
│   └── notification-service/  
│       (each: app/, tests/, Dockerfile, requirements.txt)  
├── infrastructure/  
│   ├── prometheus/prometheus.yml  
│   ├── grafana/provisioning/  
│   ├── loki/loki-config.yml  
│   └── alloy/config.alloy  
├── database/init.sql  
├── tests/integration/  
├── .github/workflows/ci-cd.yml  
├── docker-compose.yml  
├── .env.example  
├── .gitignore  
└── README.md

## **10\. CI/CD pipeline**

GitHub Actions tests, builds and publishes the container images on every push. Publishing runs only after tests pass.

1. **Source validation:** check out the code, install dependencies, run basic code validation.  
2. **Automated testing:** run unit tests, API tests and service functionality checks. If any fail, the pipeline stops.  
3. **Docker build:** build each service image, apply version tags and validate the build.  
4. **Image publishing:** push the images to GitHub Container Registry.  
5. **Local run:** pull the latest images with Docker Compose on localhost, restart updated services and verify service health.

Example image names:

ghcr.io/username/miniops-target-service:latest  
ghcr.io/username/miniops-monitoring-service:latest  
ghcr.io/username/miniops-incident-service:latest  
ghcr.io/username/miniops-notification-service:latest

## **11\. Runtime environment**

### **11.1 Development environment**

The whole application runs locally through Docker Compose, so the team can develop, test and demonstrate it without paid infrastructure.

### **11.2 Hosting**

This is a school project, so it is not deployed to a hosting provider. It runs on localhost through Docker Compose. A hosting option for later is a Linux VPS running Docker Compose, which could host the same local stack. A domain name and HTTPS would only matter at that point.

Hosting is out of scope for this proposal. It can be revisited if the project continues.

### **11.3 Environment configuration**

Use environment variables for:

* Database connection strings.  
* API URLs and service ports.  
* Monitoring configuration.  
* Authentication secrets.  
* External integration credentials.

Never commit .env files that contain real credentials.

## **12\. Testing strategy**

Testing matters because the project is made of several independent services.

| Level | What it covers | Tools |
| :---- | :---- | :---- |
| Unit | Target registration validation, health-check result processing, incident severity calculation, notification creation | Pytest |
| API | Status codes, input validation, error responses, database operations, service communication | Postman or automated API tests |
| Integration | Register an application, trigger a health check, simulate a failure, verify the incident, verify the notification | Tests in tests/integration/ |

### **Failure tests**

The team introduces failures on purpose and checks the result.

| Test | Expected result |
| :---- | :---- |
| Stop a monitored application | Health status becomes DOWN |
| Restart the monitored application | Health status becomes UP |
| Stop the Notification Service | The incident is still stored |
| Stop Prometheus | Metrics become unavailable |
| Send an invalid API request | The API returns an appropriate error |
| Stop one microservice | Other independent services keep running where possible |

## **13\. Demonstration scenarios**

The final presentation shows real system behavior, not only configuration files.

### **Scenario 1: Normal operation**

1. Start Docker Compose.  
2. Open the MiniCloudOps dashboard.  
3. Register an application and show it as healthy.  
4. Display CPU and memory metrics.

### **Scenario 2: Application failure**

1. Stop one monitored application.  
2. Wait for health checks to fail.  
3. Show the status change to DOWN.  
4. Show the new incident.

### **Scenario 3: Centralized logging**

1. Open Grafana and go to the Loki logs.  
2. Search for the failed application.  
3. Show logs from different services linked by a correlation ID.

### **Scenario 4: Recovery**

1. Restart the monitored application.  
2. Wait for successful health checks.  
3. Show the application recovering and the incident resolved.  
4. Display the recovery notification.

### **Scenario 5: CI/CD**

1. Make a small code change and push it to GitHub.  
2. Show automated testing and Docker image building.  
3. Show the image published to GHCR.  
4. Show the updated images pulled and running locally.

## **14\. Team organization**

Responsibilities are split below for a team of five. The five-person team can combine related roles.

| Role | Main responsibilities |
| :---- | :---- |
| Backend Engineer 1 | Target Management Service |
| Backend Engineer 2 | Monitoring Service |
| Backend Engineer 3 | Incident and Notification Services |
| DevOps and Observability Engineer | Docker, Compose, CI/CD, Prometheus, Grafana, Loki, dashboards |
| Frontend Engineer | Dashboard and API integration |

Every member should understand the overall architecture, service communication, database ownership and deployment process, not only their own service.

## **15\. Implementation roadmap**

The project is built incrementally in ten phases.

| Phase | Tasks | Deliverables |
| :---- | :---- | :---- |
| 1\. Planning | Requirements, architecture, API design | Project specification |
| 2\. Foundation | Repository, FastAPI setup, database setup | Initial services |
| 3\. Microservices | Implement the four services and REST APIs | Working backend |
| 4\. Integration | Connect services and databases | Integrated application |
| 5\. Containerization | Dockerfiles and Compose | Local deployment |
| 6\. Monitoring | Prometheus, exporters, Grafana | Metrics dashboards |
| 7\. Logging | Loki and Alloy | Centralized logs |
| 8\. CI/CD | GitHub Actions and GHCR | Automated pipeline |
| 9\. Local run | Compose stack running on localhost | Running local application |
| 10\. Validation | Failure testing and documentation | Final demonstration |

### **Gate before the final presentation**

The team does not move to the final presentation until all of these are true:

* ☐ All four microservices have working APIs.  
* ☐ Each service owns its database.  
* ☐ Services communicate successfully.  
* ☐ Docker Compose starts the complete application.  
* ☐ Container images are published.  
* ☐ CI/CD runs tests and builds images successfully.  
* ☐ The application runs end to end on localhost.  
* ☐ Centralized logs are searchable.  
* ☐ Metrics dashboards show real data.  
* ☐ Failure and recovery scenarios work.

## **16\. Security and reliability**

This is an academic project, but it should still follow basic production practices.

**Security**

* Validate all incoming API requests.  
* Keep database credentials in environment variables.  
* Restrict access to internal services.  
* Do not expose PostgreSQL publicly.  
* Require authentication for dashboard access.  
* Never log secrets.

**Reliability**

* Implement health-check endpoints.  
* Configure restart policies.  
* Use request timeouts and limited retries.  
* Handle unavailable dependencies.  
* Use persistent database volumes.  
* Avoid creating duplicate incidents for repeated failures.

**Monitoring safety**

The Target Management Service must validate registered URLs and block access to internal or sensitive network addresses. This prevents server-side request forgery (SSRF) through monitoring targets.

## **17\. Expected deliverables**

1. Complete source code repository.  
2. Four independent microservices.  
3. Database configurations and migrations.  
4. Dockerfiles for all custom services.  
5. Docker Compose configuration.  
6. Prometheus configuration.  
7. Grafana dashboards.  
8. Loki and Alloy configurations.  
9. GitHub Actions CI/CD workflow.  
10. Published container images.  
11. Running local application.  
12. API documentation.  
13. Architecture diagram.  
14. Testing documentation.  
15. Final project report.  
16. Presentation slides and demonstration.

## **18\. Success criteria**

The project succeeds when:

* Users can register and monitor applications.  
* The platform detects application downtime.  
* Monitoring results are stored and accessible.  
* Incidents are generated automatically.  
* Notifications are created when incidents occur.  
* Infrastructure metrics are collected and visualized.  
* Logs from all microservices are centralized.  
* The application runs through Docker Compose.  
* CI/CD tests the code and publishes container images automatically.  
* The application runs and is accessible on localhost.  
* The team can demonstrate failure detection, investigation and recovery.

## **19\. Future vision**

Version 1 focuses on lightweight application and Docker monitoring. Later versions could grow into a fuller infrastructure management platform with:

* Monitoring of multiple remote machines.  
* Kubernetes monitoring.  
* Distributed tracing.  
* Advanced alert management.  
* Email and Telegram notifications.  
* Automated incident diagnosis.  
* AI-assisted anomaly detection.  
* Infrastructure health recommendations.

The long-term goal is a lightweight, extensible platform that helps developers understand and manage their distributed applications.

[image1]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAkAAAAG/CAIAAAA/1P8wAABrFElEQVR4Xuy9eXhURfb///2/fdRH/emoPx11dL7z0RkdHZdxmVHH0fGjjkuQHdkX2fdFQHZZRFBBZUdBQHZkU/YlG1sCJGHLShKSkECALIQAWe739D2kLOp2h9vdt5Pqzvv11NNP3XPr1r19TlW9q2533/4/BgAAABCC/B/VAAAAAIQCEDAAAAAhCQQMAABASAIBAwAAEJJAwAAAAIQkEDAAAAAhCQQMAABASAIBAwAAEJJAwAAAAIQkEDAAAAAhCQQMAABASAIB843du3dfuXJFtdY5lZWVdCWqFehNIFHbbaJaAWjY+C9grutp06aNWsJHbrnlFlHb7373uzNnzrBdOsk12D5ixAjK33vvvQkJCbUUcxaqNj8/X7X6hc0rpHdnLVlaWmo1esN+yQZOy5YtmzZtqlqdw6eoKQTYpOnYRo0aqVZ7eGyBAOiApgLGnDhxwrCcyGX2pRta2Og4LgiYj9DZ16xZo1q1JFQEjDLPP//89ftvgMu7gF24cKH2GHlsgQDoQKACphh37tzJ9v/93/9lC+UXLVok8uvXr+dMRUUFvc6aNUscywImNin/pz/9iTPW7krGN954g/O7d+8uLi7mvFKJ4NChQ3xhL7zwAluqq6vZIspTRyUZ7tKlC1mqqqrotX379rzrhx9+uPvuu43rxUAcXl5ezpaePXuyZebMmWwpKChgy4MPPigOZMh4+vRp3stuMcyrotUnGy9evGjUDB/0ZtlYWVkpDucM1dyuXTveK8R14sSJbLl69aooKfjmm294L10wWyifkZHBxsGDB7OxpKSELXRJvx1cwwMPPEC7/vOf/2RmZopTvP3223zI+PHjDclFooDioueee07skouJzJ133sn248eP04SGMnPnzuVdffr0eeqppzgvk56ezoc8/vjjwqhcGMMWV825WMDuuOMOsjz55JOiGOOxbXPDY3tiYiLlX3vtNa6QXsvKynjXe++9Jw4RmalTp/Le/fv3s1FE7cqVK1yA7cQjjzzCx3IBRlQlb8qw/c0333TVCFhOTg4bb731VrkMIZwpLLzJLXDBggVsJMFj+8CBA9nSqlUrtnjsZUp7BsBBnBQwGoXJMmjQIB5Ps7OzuZhHAWPWrVsnDpe1hySB8tRDuPATTzzBnwGIjwH48NatW8fGxooaDO8CRsY5c+YMHTpU7KVMt27dli5detNNN7EWUkelE5H9r3/9KxcQhakMn0hY7rvvPsqvWrWK9IONrIgjR46cMWMGZUaNGsXlaUD85ZdfKPPQQw/xsQzXL7QkLi5OGPmqXGa1PHz85S9/+eSTT1zXjzucobd87733Dh8+nI8ly+zZs7nk2LFjhVFA+kSWyZMn81BLl821EV27dqW5AmUKCwvZeM8992zYsMFaCV/eRx99RBf22GOP8d7evXu7zBDT6M+Wd955hzJ///vfKUObr7zyist0EcsJuWjt2rUuU2VTU1Pls3Dm5ptvdplOFrvolU4tyoiJiyA3N9dlRnDChAniKOuFGebhNEOilQdlSEcNU8Ao37hxY27A1Frkmsly1113rV69mjJiNvPZZ59xhvjggw84T+9OGOW4sFFkXOYpbr/9dtlIUeN+5PIiYOxSUgV26bRp07iB/e1vf1MaGMeIvEcxctUImMu8eD7FH/7wB7KQHrvMGHXs2JE2n376aSpPBahRsTJxCyQ4WHwZy5Ytc5kd8K233qJMUlISV06e515Gu9jiur49A+AggQqYQFh4Lw1tzzzzDBs9Chj3dhnlFqI8TsmwUUwkZaOoRGwKyFhaWio2V6xYIRfjvHKrhHVILuAxQ9BYSa99+/blcZD3cgF6pfFdlJRx1XR7zv/xj3/kq6JFmzAa118Vr+fkvXJGrGbE2QmeOHOekfc+/PDDtI5hI60yRYHFixdzhi00F6H88uXLeZN30cgl8sop2Cgy4vaUq0YqOM9l6HX69Om09BGW7du3KxV+/vnnbKF2xRl52Sfz7LPPCju9C2sZtrAOsYW8yhEkARPBcpnTppqDDFraivLiGuiV5jGckZ1PCxHOsCRw3pqhVb5slN8RR82jgHF5cU+C5LaWBibnlVuIoqd4u4UYHR3NBeQWSItFyn///fdySbJ0796dM3Q9wu6xPQPgIIEKmDfL1q1bOe/yImDx8fE1x11D9Ch5cDGu764eoQJNmjThvDcBu3z5Ml8e723Tpg1l3pEwLAJmmDWfP3+e1w3CQq8kPNaz0FLs0UcfVeokaBrL5+WFnUCugQvYuSrlSuTMO+bcnC0eDxGbL7/8MudpMSSGYBERV03IlItRbr7R8MR5Ghn5FBEREZT597//La6ES8oCZnURrTn4gnfu3EkLmgEDBpCF1hNGzQqMipHr5Ar51XpXlu18iHwK64XR+kBUKJA/A3Ndfwdy5syZojy37cOHD5P3XOYtNdJybmC87BM1fP311yLvLSPypAqK0Y6AGV4amNJEXdIKzGW6QiyJFAGjOY3LnJ1QI+EC1hbYrFkzvv952223sUv5I3Bywn/+8x8+BZXx2J4BcJBgCdg///nPp59+2jA/KZkyZYoocODAAc7UImCGWYD6mMgrArZjxw4y9u/fnzdvv/126i2c9yhgcXFxPMU2zNpWrVqlrMD4zqRVwIYNG/buu++SkZcphpcBSKzAxJC3b98+rpN2lZWVGaa8KZXTJi01RJ7cxVd18uRJNnq8KusFiIwYnV0mbJw8ebL1vMJCruvduzcbPQoY32A0zItJT0/nPO/yuJbiDL19cQrKLFmyROStLho3bpw4kD8ZJTZv3szlSSQMSSOJV199ddSoUbR56tQptsjIK7Dy8nI+hahfXJg8SaLVlViBeRMweQVGbZvzLFqdOnXiT78of+edd7722mtczOWjgNFUSRi/+OILV60CJrRKNDD+1FaU52LyIk8IGH9k6zIxagRMjhFnWKKM61vgzz//THm+f8hG/riOtErpZS5ziuOytGcAHMRJAaNuTJaXXnqJZtmumlt23OIbN278+9//XpR33UjA8vLyKF9SUmLUnEhGGF944QXOXL161VqJgD9R+/TTT/kDCf4hl8v8CISMdAjN9A2LVDBcv7zJGb5lNHDgQFmZXObbpzWEq+YGlMu8F8oTczqRqId3ES1atOAMu4vzfFUuy/DBBbxlhIDx7NtlfsOCM1yAmT9/PlloUXL33XfLlXgUMGLMmDGcofFaVMKeJwfyIonr4QyvS9hCvPjiiy5zGr5u3Tr+gsxLJq4aF4nFMZdX8rQa44m8MJ47d85beeLixYsu0+cdO3YUuzijXBgXo2UlZV5//XWjVgFji8uMOL3yAlEYOc9rF/GhrMtHAeOMy/QVZ2oRMC5G+Q4dOnADowWT0sD4s0ma53GMhICRAFtdISp0mV/K6NevnyhALfBf//qXy/x2jzDeddddlBk9ejRbKEbcy2hBz73sL3/5i6hZbs8AOIj/AuYNmmdFRkbKFv795p49e2SjI9B6TnyD64bQNURFRcmWrKwsMp4+fVo22odGXjpcfI7FHD58WJlpFhUV1TL3LCgoOHLkiGIM5KoE5HBZchToFHv37lWtnqCS3r4/xu9LfCZkmJ+W8Y8faoFcpASiFmJiYniFIeMyb+3Km9JON7SSo2sT6w/Dy4WlpKRQMZ4n2YGCUksoHYGixt2H3tS8efPU3Z7gBiavjwXUtKwXTBarK2SogPgVpgx1N7klFBcXWyvPzMy0BteR9gyAFecFDDQEXObyTuStEhI8Tp48KZ/uySefzMjIkPaHKvwtVs4PGTLEJf08AwDgEQgY8Idhw4axbjE071ZLBI277rqLvyTJiM9dwgDZpeJnjgAAb0DAAAAAhCQQMAAAACEJBAwAAEBIAgEDAAAQkkDAAAAAhCQQMAAAACEJBAwAAEBIAgEDAAAQkkDAAAAAhCQQMAAAACEJBAwAAEBIAgEDAAAQkkDAAAAAhCQQMAAAACEJBAwAAEBIEiwBKyo6FxX5K5KSrlzx+hfJdcPly5esV4XkUzp1Kij/n5mVlWo9F5JPqd77F6hjgiJgB+OjqTGp1gZPVlZavbuFLiA728N/zwP7kA9jY7aq1sCIid5c720j1OEZgGoFYY3zAnboYAyakTeqqqrq0Tl06urqatUKfGff3h0x0VtUq79ER206sH+XagW+U1VVWY/9C9Q9zgvY/n3oirVRWlpUL32MTlpWVqpagb9kZJy4fPmSavWdS5fKaGmuWoG/FBefr5f+BeoFhwUsG13RBtTByssdGPvsQ9KFXu04B+OjVZPvYMLnOPgwrOHgsIBhlLRDakrSieOHVWswOXY0Pj3tmGoFgeFIa3ekEiCTkpyYfCJBtYJwBAJWD5w9m79v7w7VGkz27tl+rrBAtYLAcKS1O1IJkDl7Jg/r2gYCBKwegICFB460dkcqATIQsIYDBKwegICFB460dkcqATIQsIYDBKwegICFB460dkcqATIQsIYDBKwegICFB460dkcqATIQsIYDBKwegICFB460dkcqATIQsIZDaAuYy+WS888++6y0U19CXcAmT57sqmHQoEHqbtskJiaWll732+oXX3xx2rRpnOf6Of/666/LsRZ4NDJK2+jbty9nCgoc84Mjrd2RSqzMnj1b9kBMTExNxFxPP/10VVWVYXpj5cqVvx1jGOScBx98kIv9/PPP8i6Z3bt3qyadgIA1HCBg9UDdCBjForS0iPOOC9irr746YcKE8ePHk9sHDhyolrDHe++9l5Bw3e91li9f/tRTT3Geh1GR//jjj38rV4PcABSUtqGPgNFRcQci5U1pp2Ow9zZv3sybLGAUslGjRgnHuq4XsPz8fN61Zs2a+++/n8t4pJZdOgABaziEoYD16tWL++GlS+6nXeTm5vJmnz59REkaN/nYpUuX8t709Lp7xG2dCRgnkjHHBYz1wJBkhtSI8+Xl5fKuW265RRzIFi7/zjvvyJtyGc488cQTlN+61f3YXJcpPFFRUVz+u+++E4WnTp1Krw8//LCoQeyS81oJGKf8/BzeVEsEzMWLF11m+7/55pvZwgLG+cjISM67rhcw9q28uWTJEsP98LNS3sWrbc67TDk0LHF3SXOO5ORkyvTv3599ftddd5ExIiKC91I/FSXHjh3LeUeAgDUcwk3AsrOzKXP58uW1a9dyB6NNvk9FmRdeeIEzkyZNEkedPHny0KFDXLhuIAGL2v2LGMjqJuWfPqVeh7/ItxCJlJQUGqH++Mc/8l6XGRSaEOzcuZMy33///ZgxY4SdGDJkyNChQw1PKzCjplizZs0qKyv/+9//0ub8+fPZKGpwSYPpqVPu93X77beLvaKMnA+SgDmS1HoDht4mLZE5w1GQbyES5C7eqwjYihUrKBMfHz/BhGcPomu4JP9zxhr3Bx54gF6/+uqru02EnSpZuHAhb7755psbNmxge8+ePUVtTgEBaziElYA9//zzlKEpP3fRgwcPsl1GOeoPf/gDbd50003Lly8XxmBTxyuwg/HRjq/A+BYiuY4fb69IWlJSkiF5vmvXrryp1ONNwNatW8eFExMTKfPkk09yZEWFxIMPPsgWPoqm8Er98qar5j6ny2kBU002EHHZu3dHkP6dgN7mK6+8wmtc1ioWsHdMFi1aJIopAkZxpMy8efPYyTTVoM39+/fzpssiYNa407Fr1qy59dZb58yZw8X4NTc397bbbuNijz/+ONvpSlzSetopIGANh5AXMPH/IK7rv1BAqzG5/8hYLTTftxqDR50JWHzctc9aHBcwXtC0bNmSRIgyNHPv0qWLXKZHjx58z3bJkiW+Ctj7778vCvOQRxN2zl9XVLJYIyhvumq+kuDSRsDEv2L6V0ntsNMExvW3EOVitdxC3L17NwsYGSsqKjgjSnLGGnfirbfe4gL0unbtWpEXi0IWsEaNGtHE0XpVgQMBaziEtoC1aNGCex3xt7/9jSykZ8LyzDPPkOXtt98WluzsbMMytDF33XWXMAabuhEwmSAJmGE6UNyqZR555BHaFJ9XtW3blgUsLS1NlOFjxX2ta/WajB49miyvvfYab77xxhuiwMMPPyxqqKysNMyT3nzzzWzJyXF/pCSg9iAKUztho0sDAVNwpBKZhx56iBwrNukt33333XYEjKB1m3AakZmZycUYjizx+9//njb/8Y9/eNxL+TvuuIMytG6m/KpVqwzz1iIXa9q0KQsYl1y2bBnnHQQC1nAIbQFjUlNTFUtRUVFZWZlsiYuLkzdlLl++fObMGdUaTEJdwLxRWlp67tw5sZmfn88fUMnQvJ61x28OHDigWIqLixWL4PDhID7135HW7kglzkIxovmHYpE3FZS4e6OkpESxuCya6ggQsIZDOAhYyBGuAtbQcKS1O1JJKJKSkgIBAwECAasHIGDhgSOt3ZFKgAwErOEAAasHIGDhgSOt3ZFKgAwErOEAAasHIGDhgSOt3ZFKgAwErOEAAasHzp49XccdjPSysDBftYLAcKS1O1IJkDlzJu/A/tq+dQLCBghYPZB5MuXoEa/figwGSYn7s7PSVCsIDEdauyOVAJmTGSeOHY1XrSAccVjAEhP3qyZgITpq02nnHuxkh9zczJjoLaoVBIYj2uNIJUCG+hc/ZxKEPQ4LGBEb435+GvDGmTN59TJm0UlxF9FBjh1zP6jMEZKTE1UT8JeCglwSMNUKwhTnBYwGypQU96PwgEfIP5WV7gfz1DEVFVfrRTjDkvPnzzjoTKqqqOjGPwQGdqiv/gXqBecFzDDbUMLhvaoVGMae2G0XS70+NiLYlJQU7d2zTbUCH8nIOEEtvKoqoOeJyFRUVFCFmZkp6g7gI7ExWy9eVJ/3AcKYoAgYExO9JcryzxENOWVna/E1iqysVOu1IdlPqkOdw3ouJPvpVHbd/aUf0IQgChgAIJyICqZ4A+AHEDAAgC0gYEA3IGAAAFtAwIBuQMAAALaAgAHdgIABAGwBAQO6AQEDANgCAgZ0AwIGALAFBAzoBgQMAGALCBjQDQgYAMAWEDCgGxAwAIAtIGBANyBgAABbQMCAbkDAAAC2gIAB3YCAAQBsAQEDugEBAwDYAgIGdAMCBgCwBQQM6AYEDABgCwgY0A0IGADAFhAwoBsQMACALSBgQDcgYAAAW0DAgG5AwAAAtoCAAd2AgAEAbAEBA7oBAQMA2AICBnSj4QpYSnISdUgk3VKkxYKkTfpF7UUA1CsNV8CiMJ3UEsRFWxAaoBsQMKAXiIu2IDRANyBgQC8QF21BaIBuQMCAXiAu2oLQAN2AgAG9QFy0BaEBugEBA3qBuGgLQgN0AwIG9AJx0RaEBugGBAzoBeKiLQgN0A0IGNALxEVbEBqgGxAwoBeIi7YgNEA3IGBALxAXbUFogG5AwIBeIC7agtAA3YCAAb1AXLQFoQG6AQEDeoG4aAtCA3QDAgb0AnHRFoQG6AYEDOgF4qItCA3QjYYoYFHSf/RFR21Wd4N6IjFhrxwadTeoP+S4HD0ar+4GoJ5oiAIWG7NV9MarVy6ru0H9AQHTE8QF6ElDFLDKygruilh+6YZYhOXn56j7QP1B4eC4YPkFtKIhChiRlZmKuaSeUFwOxkerVlDfHNi/C10G6EYQBazptycfHXIMyb80d1eh6lCH2JRYYj0dks308mcpqkOd4x/jkq1nRLKZth4pUR3qELN2nLWeDslm+tunx1WHOkdQBGxLEoZIZ5Lq2YCxngLJj9R/icN3OHv9eMp6FiQ/kurZgLGeAsmPtPrABdWzTuC8gD32iftyey86lXvhKlIgiXxInoxKvqi62C/OX6yk2v4zOc16IiSf0tK957lPqi72F65t7cEi67mQfEqvTkglT5ZerlJd7Bfbj5VSbZ8sz7WeCMmn9O+J7rg8PtSxLiNwXsDoQtvOzrK+ByQ/koMDJVdlPQWSH4k1LO/CVdXLvpN+5gpVterABetZkPxI6DJ6ppYzM52Ki4zDAtZjQTZC7mDaesR9M7bL/CzV0T5C63eqZ8gyzCUdS/8Yl/LEMAc6JMXllfGp1vqR/Et9FrvvW2xKDPTzsL5mPTuPl1pPgeRfIn8OWpqrOjowHBYwusS0givWS0fyO/11+PHAZy6YSwYjBR4XwwyNtWakQBK3dtXRPkI1PPXpcWvlSH6n43nlgcdFwXkBs143UiCp9SwHlt4QsGAkcmlBcYXqa1/IMO8fWmtGCiQ5JWBdvs+2Vo4USAo8LgoQMN0T3xJRHe0jVMMTwzCddDiRVw9mXlJ97Qt7Ui+iyzienBKwQUtxy93hFHhcFCBguicImLYJAqZngoBpmwKPiwIETPcEAdM2QcD0TBAwbVPgcVGAgOmeIGDaJgiYngkCpm0KPC4KEDDdU0MQsKEjxx087sNvB49k5Pt6SDBS2AvYlsgD5GerXfMUfgJGgRgxdpJipNB8PWO+tXDtiY5avyXKaq+bFHhcFMJKwOYtWuG6HmsZX9PaTbutxrpMISFgn46dSN7+fskqYfHJ/1Ry0659lNkWczDl1HlrASXFHDwuDqnHFKICxsGy2q2JxkdrSbJs2BZjLWxN+5PSVm3cbrUHO2kuYOTAp5/9u7xpLcNJeI8C8bvf3S3KE9/MXkCvL7/6b+tR1nQ88+yO2MPi8LETp1rL1E0KPC4KYSVgu/Ym0PziqaefpSBRxpHJ4/9/3/1WY12mEBKwW2+9lTdXrN/K3cxasvb05tvvbouOt9r1TGEvYB6TfQEL8ER+J/0FjFiyaqPYtJapZZdHY+2JZuGNmrSw2us+BR4XhbASME5NWnzEMU4/XUKZZ//+Ar0OGz0+14x95269eS/N37klMXys2OS5j7K3XlKoCNichcvIUUdPFuSafus3aLjwm3Djsp830Sb1pT888ke20KKZLL9/4MGss5def/NtUVI+6qabbuJ6aL4p76VDaHrxr3//h43/3513kn3Sl9+Ko1y2h1r/UqgLGL0Knz/z3PNkGTh0FG8SI8d9TtN2Lrl87WY23n33Pa4ar4qSf/y//5NrTvWUWIgC1msIatJfwMiBwi1yhuEGLzYpT4F47fU3FaPLHM0ow01d2HnXX554kl7jj2XSUCbvpdcV67bIVT3w4EN8lBK+YKTA46IQzgJG6wBehLVs3V4E76GHH+FilE9MdTdQGnN5b6/+Q8Z9/pXYyxmswOwkGhPnL17pMgdEnjfk1vjw4x59R4//gouxhQRs2KjPKLNxeyyHgwUs9/oVmAgBZX5cvpYzCSk5wsgCxsXoFOKkfF+F+y0EzJpkASPPU+ad9xoJC+2lzN9feInyQsDo9W9PP0uZH35azV594aV/8q60vGKOizUWWIF5TOSTpLS8D5u1pGkcb+aa3UT4ypoRApYrjUiuGgGTy9Mgll1YPm3m97QZHXeUNCn3+hWYSxIwYTmSflqxcMbxFHhcFMJZwCg99bdnXDXkmoGhuSTvkoPE+VtvvVUUFnshYHYSDVW0lqLOQ3774MNmwtu55vRQFGML9SVe4JIC8QBqFbCc81dECCjz9rsR4nBhlAWM+qQ4qRxiCJg1KSswygwaNpryss85yQK2aMV6NrJXXddDC19rLCBgHpPLFDDO8A2D3JpVlCigZGwKmEi33XYbx+XRPz+e60nA1vy6k0PPllGfTZbrsVboVAo8LgrhLGAcQsr8+fG/Cov4XJSWyV9+O5cyM+Yt5r00/vKdxlzzuzqcEZ/r1FcKIQHLrfH5gaR0ztNr9z4DO37cM7fmjm5urQJGQvXT6l+4Trk78QcGwsJ5bwJ25113UaZ9524uCJin5E3A2NKuU1fKPPHkU67rV2D/8+ifKfPFtFnsVbECyzU7C0XcGgsaFkWZukyhImD06jLJNbsJZ0Q34ZKcuaGA0VGc6T/40yGfjqGA5ppf/WABo3j985XXxFEeVmAZ+YqFM46nwOOiEM4CRmrE7aN77wFscUkCxpvESy+/KkeO4RYgLAuWrrGeqG5SaAnYc8+/KDtTZJiYg+5rqEXAaKrIJSl/8803c57LyBVy3qOA8R0tolPXXi4ImKdUi4DxHUJm6ZpfhYCJb+U88OBDwquiJE/yrLE4nnmWC1ivIagpVASMkvxRsccG7zIHn9oFjIPC5Jo/MuH8Y395ggVMVHUs84zL8hnYK/96XZRRMo6nwOOiEIYCpqQTWYVWo5LkgNEgy4OpJikkBOyGaXvsIavxhim7sHxfov9/NUJhPZwcxD9WDVEBu2Hy9t136+8WMs+UWYvVe9JcwGpJ/nUTTnLUkrPP2amKZnv8ras6S4HHRSH8Bcxb2hZzUMxBUnP0/TtBvwUsKvLXqqpKzte7gNVZ+m7eIhHWHn0HWQs4mPwTMIpLRsYJzuspYKGe/BYwCo3I14uAhX3yLy610HAFLFRSIAJGKTZma2VlRcMRsLpMfgsYpyuXyyFgwUiBCBilxIR9BgQsOMm/uNQCBEz3xAKWlZnqaxIDJSUIWDASefXXvSlWz9ee5LjMXr0TXcbxxAJm9fwNk9JlIGCOJwhYg0sBrsAoxURvgYAFIz0a2AqM0s7EAnQZxxMLmOp3G4i4HD60BwIWjORfXGoBAqZ7CkTASLquXr1qNKTPwOoyBSJgR5IOGPgMLDgpEAGLj4viPAQsGMm/uNQCBEz35LeApaf/dhQELBjJPwHjj1gYCFgwkt8CVlCQK/IQsGAk/+JSC9oJ2I6YOE4Zp4ute60p4oN3V2/YYrWHTfJbwGT8E7DYg8c5FsdOun/n6F8aOGiw1egtfTJ8uLx5JD3v21nzrMWU5NMp5i5YZDX6l/wTMBkHBUx0HEppuXa/VXtD1/Xt17dz505Wu5xOFlykbihbblhtUJPfAibjn4BlnilbsnJtdNxR6646SN/MmisCMfHzL6jv0OaGrXb/T0M+PEgp8LgoaCdg5MFZ8xZSat++7bQZs60FlETd9bjlpwyt23xkLWknBR4/v0/tLdWjgNHg9eU06gULe/To0advX2sBO8knl3Lhn1atXbTc/cvxQ8dPDhsx0lrM41E207iJ6v8q+Z20EjAK03ez57do0ZQyR2p+J3vDdEPX0SQm+kCS1S6nU+cuUzeULTes1qdivqZ6FDB6RyvXbfp8ylfJ2e6fn1JLtpZxPP3WX05kcSAaf/jBUfPhGrSZnHXWekjthwcvBR4XBR0FTMmv37KrVauWX02fwUbqLdRLN+2MYcvYzyawnUbbHr3cjywiO8VPzAEHD/mk/8CBNEmk/Oixn9Frq5bN6XXV+k1UPiXnvDjdyrW/0hn5wMTUnK7dug77dATvIuN3c+b/sGgZ5al1du3eLTX3wo7Ya4+d7dSp42fmsKicmi7JzgKi9lS/AkYSwnmOxbwfl/Dmmo1bc023fDpy1JChwygotBm1P7FVqxbxR93PkRKJDpwy7ZtPhg3nMpRGjhkroqn4mQrvPXyiS5cunTt3pgwLGLl34U8r5DopjR43nuziKBq1e/bskVqz8qC55HBJ+WbM+b558ybck4WAcZg8XrPNpJWAUUrPK+7QoX2uuXJd+8v2pavdTy/MOF3cb0B/8gCXISfQXGTAoEG8yWGd/+NP07+bRZlxEyZy7xBp8649VBVXOGHSZBGI/YlpXT7uIpzMzqQQU81bdu0RvfjHn1Y2b96Uex9VQjFt164tV0KHiO52PPMMnXfzrlj51H6nehQw0d/XbdrJLZneIGXIMuWraW3btt4a6f4x+KYdMdTkxNK2Z69ewpPZheU0vLCiiEQDF80kaU5PGsMWGo4+GX6tT3F/oRMdO5nPF8COpQFt+MhrTxRavGINBYKugTdX/PxL9x7duNlbD6dG0qtPb3E7RDm7xyu0mQKPi4KOAkau5Ma95pdtZEkynxlPiaY2XECUpFfusU2bNGIju1gsg5o0dj8ElhKNbvRKnUf4vb15oLeZo7Dv3uv+IzhhX7rq2iNNqU+u37RT3sUZcWq+pJScc6LN+ZfqV8BosKNY0Hvhpk9DGO9iJVPeO796c6lcxlpY9rO8AuvYsQNllqxcO3PuD9Y6efjzdooPG71vLUwClpCS3bp1K/kQ/yae2goY+U28a35rqzdumfuD+97pxM+v/TMAaVWu+fZbtmjOTfT7RUtpyBOHcCILzdusgeDOyEdxPeJVZKj35Zy/kmv2PpqpiMkQVSIXE5k9h46LWU4gqR4FbOacH0yXNuNNsQIjAeDMvoRkel22ekPHjr9NvzgjN9fDyVkpp86JamngkguLQ6gZ00Ak+gs1bL5jIQrQ5CzXHIWEY09knaVEJUUx6+GTpnzJhUnzcr2cXblCmynwuCjoKGC55lPydu9zj2hxSelk4TRm3Hia99F8Xy7JPZamDBR+svCzbYSKiGO5sIgEJVo6kFGESq6T0tjxE/ioX3dEy3Zew3ESAiafQpyaL6lZs8YBPm6nfgWMB50531/73Kh2AaNeShlabMmVyGXkaLLdo5+ttxBpLy2qRJ1Dh3/q7RT8KhKfUS5MAiZbPF6zzaSzgIlbrzykUuI1VnTcEfkQsrMCcaIOQpadsQeFRQiYx0DI9RxIShNzdmsgSLSEgHGsRTFKq9dvpnz3nt2tNfuR6lHARGJ9EgL20UctxS5a6JCA8e2cXMsAQipOGVqrybV5lJBc89bCz79utyqQKMACJmYMItHyS5zRerhoJFxAObvHK7SZAo+LgqYCJjI0cVAmZUoB7rEicbuRBUzeKwsYp8YffiBvivKDhgzhjCJg6zfv4ox1BcZJ+QzsaEa+mGr5l3QQMPEeR44ZyxnuEkosONF0WyyalTIUSjE55eTRz9Sjfly2Kte7gImF9ax5C8VRIqNERGxy4c8mTtq0M0Ys2Tkp12wzhYSANW36Ya65TmIBIz1j+4LFy3NN59A0K2p/olyP7EBvArYtaj8X4B5Bh2QXlove5DEQtQgYpynTvlm1/trCLpBUjwIWaz6uOldqybwppJ0/sFcEzFoPjS0TJk8Rm94ErMvHH9NKSPQXbwIWe/C3NpacXUgrAZ6jKN1NHC7udnAB5eyclCu0mQKPi4K+AkbLXs6P/cw9SReCT4PgwEGDN++K5b3cY3fvPUwdVfavyNMaiPL8mY0sYLSSI7toRpxWb9hCxpj4oz179aLM2l93KAJGicJGF5Cae4G/3sNfwaKz8KemuTW3AviSyC7X70fSQcByazywbM3GiJqJmzCKDHUMyoyf+LlciVLGffuuzUcUTX5isjc/t+/QzuO4yenQiaxWrVpSYf5wxXo9ffv1oyiIL4P17tOHdu3aeyhX+gyslmu2mUJCwGhxSW8w43QJC9iiZasbRbzHTTS3xgm0nqYlAvWsLl26kCUxNUfU6U3Avpz+XYTZ7OV6og8kkYbRFIHv1rrPPtx9du59VgHj7kaZ6TPmUKbfgAHivIGkehSw4SNGRkgdJNf0DA8y7FtuabKA5Zojhmiu1MUoQNT+5WqtEkJNmoYXvvGea/YX2uVNwHJrhruPu7r/K4emGs2bN6WGQR3c4+ELf1pBmzz1ybWc3eMV2kyBx0VBOwGrPZHrW7a49iGz3ErqLPG8Nde8D8D394Od6lHAkGpPugkYEqd6FDCk2lPgcVEIMQGjNG/BYp7jnLjR10ODlPjstAKw7gpGgoBpmyBgeiYImLYp8LgohJ6ANbQEAdM2QcD0TBAwbVPgcVGAgOmeIGDaJgiYngkCpm0KPC4KEDDdEwRM2wQB0zNBwLRNgcdFAQKme+rrkIAhNI4ncunhrIAEbG9aGeLieIKAaZsCj4sCBEz3FPF1euBRh4AFI5FLiy9Vqb72hfxi959lW2tGCiQ5JWAtZlz73j+SUynwuCg4L2Br4ous143kd3KqN2KgdDblnHemNyIujid0GT3Tkj3nA4+LgsMCtnzfBUTdwTTgpxzy5+LY86qjfYRn+i+NdT+HDcmRRP5sPStTdbTvNJqWgS7jYHpudDL589zFStXRPrL+UBHVM3yV3ef6I90wkT83Hi5WHR0YDguYgZmLo8mRuSTz/Bh3x7aeAsmP9O+JqU7FxTC7zJuT06xnQfIjkTNf/ixFdbFfYChzMDk4lMk4L2DdF2Qj8IGn3cnu76dRqqpWPew3XOGsne5/KkLyO7EbnRoljZq5xWOfoMsElKZvPcNuVP0bABzryBT3E8uQ/E7sxkFLf/vDa6dwXsCYTvOy+KKR/E6O3KFS+HxjvvVESD6l1yamVjs3q2BomvLK+BTruZB8Sl9uKlA9GzBNvz1pPRGST6nXj6dUtzpEsASM2XGsdO6uwm+2ntEwDZoXazXqkMhjqfmXVVc6yrmLlQuizllPrUPSKi6D5+2ZviWf8zO2n92UWKK60lEuV1RvSiymE1mvRIekVWjktDD6XFFZoB961U7y6ctzMJT5mCgux3PLVVc6SnAFTGeiIn9VTUAD9IlLRUUFXUxszFZ1R0NFn9AAmYYcFwgY0At94kJXwikrM1Xd1yDRJzRApiHHBQIG9EKTuJBoCQHT5JLqHfhBTxpyXCBgQC80iYusXlFYhJloEhqg0JDjAgEDeqFVXJJPJKimBoxWoQGChhwXCBjQC63iAgGT0So0QNCQ4wIBA3qhVVwgYDJahQYIGnJcIGBAL7SKCwRMRqvQAEFDjgsEDOiFVnGBgMloFRogaMhxgYABvdAqLhAwGa1CAwQNOS4QMKAXWsUFAiajVWiAoCHHBQIG9EKruEDAZLQKDRA05LhAwIBeaBUXCJiMVqEBgoYcFwgY0Aut4gIBk9EqNEDQkOMCAQN6oVVcIGAyWoUGCBpyXCBgQC+0igsETEar0ABBQ44LBAzohVZxgYDJaBUaIGjIcYGAAb3QKi4QMBmtQgMEDTkuEDCgF1rFBQImo1VogKAhx0VHAausrMzMTElM2BvUFBX5i9XoYDp6JC7zZIr63kKc7Oz048cOWd+sgynYcaGUnn68vLxMfW+eCBUBu3TpYnr6Mes7dTYFOzTUtE5lp6vvLcQ5eTKZhgLrm3UwBTsulGhArqqqVN+bBmgnYFHm/wcePBiTlZka0ikt7dihgzH0Xqhbqm8yBKGRhd7Lvn07U1OSrG82tFJiwj5uZuqbtBASAsbvJTFxv/WdhlZKSUnau3cHvZfcnEz1TYYgx44epPdy6FBsetox65sNrXQwPtpml6lj9BKwmOgt2VlpqjXEiY7aHBO9WbWGFPFxUdR2L18uV3eEMufOnblhh9RfwOgtFBWdU62hDC2O3VPY+Gh1R0hBbyE2ZotqDXFoHRYbs1W11isaCRiF/OrVq6o1LKiouEqzftUaIpw+nX3hQqFqDReo1VF0VGsNOgvYlSuXbyjAocvZs6fPnMlTrSECqW9FRYVqDQsuX76kVavTRcAo5EeOxKnWMEKrqPtE6F65HQryc2p5gzoLGF124dl81RpG1BIXnamurg7RK7dJQsLew4f2qNZ6QhcBC++QE/v37czKSlWt2lNWVhr2oanlDWouYKopvHDfkrlyWbVqT0b68QP7d6vWMEIrhYaA1RFFRef2xG5TrdqTlnokLfWoag0varmtr7OA7du7QzWFF+T8kxknVKv2REVuKi0tVq3hhT7DNQSsjgjRpUxY/hhA4cD+XaqpBp0FLD4uSjWFF7SUCcVv8FI3Ly+/pFrDC32GMghYHQEB0xYImJ5AwLRFn6EMAmaLO+64g1537979zjvvqPvsAQEjXC6XavJO165dfSrvEa6BokaxU/fVEMYCRm//xIkb34Wzunrfvn2vv/66bAkE/+LYAAVMOGrAgAE333zzrFmzyLJo0aLrS90A/7wtwzXU0mX0GcpCWMDuv/9+1eQXLVu2VE0WIGCOILrEP/7xj+v3eIBG3lq6kE0auIDRuy4ru/EzR6yuti9gdoZLO2WsNBwBGzJkCGdEFMhj1dXVbMnPv/F3TRMSEkSfqqWp2wQC5jO+eqRp06a33HILDUwc3Y8//vj3v//9nj3Xvtw5dOjQbt268cxlwoQJJHULFiwQ2kOWe++9d8SIEZQfO3bsgw8+SLu2bvXwSX5qauojjzwSHR0tC1iTJk3+/e9/FxUVqaVrJZwEjNz78ssvt2vXjvLPPffcuHHjxK7OnTu3atWqstL91BnqltQJyV3Tpk3jvRwCer377rtFOAYPHnzfffcVF1/73HvJkiXbt2//3e9+l5SUNGjQILK8++67P/74IwXx4sWLXIaiSZuTJk3yNp+gGp599tlTp07JAkaX2r59e7VoWAuY8A85s2PHjk8++aTY1aVLF2r55EPey64mOnToQHlZwDp16tS2bVvOKzFNS0sjD9NZ6CguIDN//nzqlZMnT5YFjGp75plnpFJeCQ8BI+dkZWW99NJL5FK2FBYWkvHVV18VBR599FHRNQxzcGOv0uAmIpiSkvLKK6+88cYbvElQC2/RooVhRoFqoz7FURCHbNmy5eGHH164cCFvkj0qKoraQHZ2dk0d1zF+/HjqVjRsCgHjWNNwp5TUZygLVQEzpBVYQUEBZ0aOHMkZ0WHS09PF/IWNK1eu5KkN8e233xreV2A0aFLDokxVVZWIqKiZ5FMufEPCScDYCbGxsXfeeSdlFi9e3LhxY2HnzLlz56jDDBs2jDbnzJnDI6AoIGaLwvKnP/2J+ptsiYmJ+d///V/ZIjKbN197sok8MgpoNtOsWTPDbBhcgK6EBmveaz0kjAVMvNl//etfnHnooYcMc9rBm3FxcRUVFbKruXdQMRYw2flUspaYKlA9X3/9NedFmbffflux1EJ4CBi907Nnz1KGtOToUfcXeoXzhRPECsza1EVm9OjRsoVm4fKmvAJjC51l2bJllDl27Nhdd93Fdg6uR+fTUCkklgvQcDdmzBjZItBnKAsHATNMEXKZ8KbI0OxelGEjhZlLEjQtMrwLGO2lCQvnRURp5cEW0TltEn4ClpmZ+fjjj1Nmx44d77333vr16z/44AMuQO3+s88+43WPKCAONCQBu/322zlDayYe3d588022eBOwtWvX8qa8S8ZV01E5b5gCtnHjRrbQRFWUZBqCgInxjideit/Y1efPn7/pppvYsnXrVhIwimlNX3Gzbt26WmKqQIVFXpQR62xvR8mEjYBxhjxMfqaMuFHkMucEhg0Bu3DhAm/KPPDAAxwXw5OAyR5WLB6dbx0q5VuIyiH6DGXhIGBz587Ny3M/dea7775ji3C3sAjjf//7X2FhvAkY9dUNGzZwXkSUh2xi1KhRoqQdwl7AIiMjxTS/T58+tLqtZbATnU2MmMuXL+dAiBsg3gQsMTGR1sSyReHmm29WBkqqk5aJskUGAsauvnLlirAvXbqUBIxi+s9//lMuWUtMFXbt+s2rokxWVpZiqYVwFbBNmzYpu24oYFevXi0pKWGLxwKBC9j48eNFngtAwHzAD49Mnjz5iSeeoJl1fHz80KFDW7VqRRbepQRPwJZbb72VokUz8UuX3O2MJkT33XcffxigQIdQz6cFOI+tFFE6xbhx4yIiIvhTMfuEvYAZ5g0ispCMPfbYY0atgx1laGTMzs4ePXr0PffcQ04WS7EbChhnlJgqcOBIHXmWwysw/jS0TZs2SuEGKGA08f/LX/5CRi4gXN2uXbt77723c+fOq1ev5luItKp+6qmnXnrpJS5pjen777/vMj+w4fplyE4d7a233hKXMWzYMBqse/fuPXv27OvLeiBcBYxC0LFjxwEDBkydOlWUqaWpiwwtkgYOHMijHLVtDp9cgKPAFgox+59e+WMUa50KLrPXUOflAhRoagM83MXFxckl9RnKQljAZE6cOCEm3d6Qw3bw4EFpT20cO3ZMsVRWVpaWlirGGxJOAlY74vadfWgKoprs4a0rEtbvbonPShXCWMBqh9ayqskLfj+a1mNH8xYIhfAQMI/QYtfXb4ERtAgT32MiaH0s7fQMf+pmn0OHVId7HO70GcrCRMC8UVhYSHMWwwykfJPXIytXruQZTS3Dot80HAGrA959913D/X8o5/i2Sb9+/QIJXIMVMGd57rnnRBTkW/d+E8YCpgMiWC7fe40+Q1mYC5g+QMC0BQKmJxAwbdFnKIOA1RHFReejo659eBtC0Age9g/z3RPr4SeAjM4CFv4P801OTE09olq1h4YyPMy3zoCA1RGZJ5MPHYpVrdqTcyojvP8bwqi17eksYLVcdniwd8+203mef3KrM3EHIk9lp6vW8EKftqeLgO2J3Rbet6rMkPv87QYd0KexBoOLF0tqeYOaC1h5+Y0fExW61BIXnamqqgrRK7dJetqx/ft2qtZ6QhcB4z9J8+MLbCFC9T5tQu4raalHL1367btPYYb7hk+J1++D6SxgRUXnw3igLCsrPXkyWbWGCHv2bAvXoYzlWZ93p4uAEWfP5IVrhwz19xUVmv+Ne0NiojcnJR1QrRI6C5jh/h78/tgY9/O3wowrVy6HQZdRTWEBva/CQlu/gqgbNBIwhhxEKSP9eFHRuZBOhWfzMzJO0HuJO3Djn2voz7Gj8fRekpMTzxTkWd9saKWsrDRuZuqbtKC5gDH8XrKz0qzvNLTSmYJccji9l+PHQ+/Lh1YO7N9F7+VkxonCwnzrmw2tlJ52zGaXqWO0EzCivLws4fBe9lfoJpoaJxy+9tCzsOFI0oG9e7ZZ32xopYPx0RcuFKrvzRMhIWDE+fNn6E1Z32lopb17th9Juu6JD2HA4UN7aCiwvtnQSjQg6/nbAB0FDABNCBUBA6BhAgEDwCsQMAB0BgIGgFcgYADoDAQMAK9AwADQGQgYAF6BgAGgMxAwALwCAQNAZyBgAHgFAgaAzkDAAPAKBAwAnYGAAeAVCBgAOgMBA8ArEDAAdAYCBoBXIGAA6AwEDACvQMAA0BkIGABegYABoDMQMAC8AgEDQGcgYAB4BQIGgM5AwADwCgQMAJ2BgAHgFZ0F7NDB+Jkzv1OtADQkIGAAeKUWAausrGzerPH69et4c8OGdS2aN83MzKR8YeFZeh00sB+9Llv6U4vmTX78cQHl9+/bl5ub06N715kzvhX1TJgwbs7sWWKT+WLypE4d28fFHaD8pInji4qKOnZom5eXx3sXLvihXduPrAI2dOjgcePGiM3Jn0803H/WfO77+fMoU1xU1K9v7507t/PeyN27Nm36ZeyYUcOGDmHLihXLUlNTa44GIASAgAHglVoELOKDd+mVRv+srMzZs2bMmjlDGEmlWrZoWlBQQPlFixbS66fDh9Lr5k2/dv24k2GqWp/ePbl8aWlJRkZ6q5bNf6vaFBveS68d2rcdM3rkxYsXeXPKlMlffzWV98oCRpWfOpVdVVXV+qMWbOncqT295uefHjXqU7KLw5cvW0qZtm1arVmzijKku9XV1VyhqA2AkAACBoBXahGwj1o1T0g4zHll6CcBkzcTExNWrVxhmBpDUsdGU7pKSbeWLF5ESamhoqKCKqe1mmEKmDhEvBK//vqLLGDCnnPqFGdkAZs7Z9aE8ePkcw0a2J+L0dV+PmmCYa4F2QJAqAABA8ArtQgYEx0V+fXXXwrx2LTpl+LiYlnArly5Qq9CwAYPGsB2OoRWRa1aNhMlBRs3buBMi+ZNDO8CNn3617KANW3SiDPiJiGv6k6ezCB9Wr1q5c8/rxaFiTFjRok8LdoOHNgv7QQgNICAAeCVWgSMhCQ2NqZN65bJySeOHjlCm1FRkawusoCNHDE8cveur76cYpgCNmTwAFpatWv70bKlP5GlS+eOX0yeNGLEsIED3B+YMTk5OT/9tHj+vDnjPxtrWASMTtqs6YdUyfJlS2UBo5UWHRIfHzd06GC2fNjofV5vlZSU8OE7tm8jrYqNiTauF7AzZwqUJSAAIQEEDACv1CJgxLFjR/nTIyY1NUXaeY3y8kskLZwnAaOV0Pnz564v4oHMzMyKigrVKpGV5f62iAKt9mhVV1lZKSziJidTXl4ubwrokL59e6lWALQHAgaAV2oXMF9hAVOtTiMLmE2w/AIhCgQMAK84K2AAAGeBgAHgFQgYADoDAQPAKxAwAHQGAgaAVyBgAOgMBAwAr0DAANAZCBgAXoGAAaAzEDAAvAIBA0BnIGAAeAUCBoDOQMAA8EBU5K9yysrE/4wAoB0QMAA8kJycKAuYuhsAoAEQMAA8I9QrPe2Yug8AoAEQMAA8U15eRuoVE71Z3QEA0AMIGABeiYrcdOXKZdUKANADCBjQl7gDkcqXKZB0TrExWysra/sXGA0pL79kfSNIHlNpabHqvvoGAgZ0JDMzZd++naoVaE9iwr7Dh/eoVl2hQTk15YhqBV6gXklzFNVar0DAgHacP38mCl/8C1kodinJSapVPw4djL182fM/fAJvxMdH79+3S7XWHxAwoB00AlZUXFWtIHTQf/5x9eoV/S9ST7S6lwgBA3qRmLAvOTlRtYKQorCwQHN5oMsjDVOtwBbV+gQXAgb0Asuv8ECfMc4jml+e5ujjPQgY0At9+gYIBM3jqPnlaY4+3oOAAb3Qp2+AQNA8jppfnubo4z0IGNALffoGCATN46j55WmOPt4LloAVFBQcPfLbDyyGDR2yY/s2ab8zULXyZvduXVJSkouLikaN+vT8+XMRH7wr73WWgwfjT57MUK0gYPTpGyAQNI+j5penOfp4z3kBW7RoISlHdFRkenoaZVp/1JKMlFm29Ce1aMB4lKjCwrOyPTY2xmMxb1DhH36Yr1ot7NixXVZo4BT69A0QCJrHUfPL0xx9vOe8gJEArP15DecrKipYPOh1woRx9EqptLT0ypUrnO/fr484ihPlp0/76ttvp4sDRQF6JTnkYrTMko+aPHkSH2hIAiZeOUVFRSq1CbhAi+ZNe/bsxnkSJ754TlSGLlveZAHjNyJXBQJEn77BZGVl7TaJiopS9znK2LFjExLC5/8zdYujQh1fXmVl5fTp08+fP6/u8MLBgwfff//9d955R92hB3XsvVoIioBZNyPcS7EWlBn6yWDK//TTYrYvWbyIXseMHlleXk6Z/v37VFdXkw6JStq3byPXw+WHDR3Sr29vNpLMiL0eBUxegVGG9k77+iu+GCYpMXHjxg1GTeURNSswWkSyEpOlrKyMXr/++kve3LZ1CwsY5SdO+ExUBQJHn77BTJ482SXxxRdfqCUCgCvnfMuWLUkmr98fwugWR4W6vLx7771XbkLqbk9QsUceeQQCdkOCImCLFi3kPK9a2Dh//lzK7N+3jy2FhYVCqOg1IeEwp4sXL5L9w0bviwpJ1dq2/Yg0j2tbs2bV4EEDOrRvywdyGcrk5ubcUMAOHNgfUbOEktm/f1/HDm3FUSxgnw4fSpdBl8SV0+uZMwXiEBIwXlOWl18SRhA4+vQNRtaYiRMnUv7bb7+l11WrVrGdJjc8MInh5tpA5XK1bt2aM8899xzv6tu3L1toYTdhwgRR0jAFbMaMGWJTruqWW24Rm5yh0Y3nfL169eIyly7p1Q51i6NCnV2eNaBLlizhDC246ZVmLWKSlJ+fLw5xmS1K2UUMGzbstttuI8vmzdf+6IcLiEZSB9SZ926I8wIWExNNw/rs2TN37txOmQH9+xqmKrA8NGkcQYuq0aNGdOncke30umzpT+vXraVMr57dq6qqFAETx+7bt1dojBCwvXtixY1KjwJ25EhSRM0tRzZ2/bjztapNVq1cQfokyjf+8INOHdvzJl1nfHxchClgLZo34eUgbebk5NC7O3r0CK0F+SjgFPr0DUYIWHV19R133OGqEbDbb7+dFMgwh4+dO3fGx8dzMbbMmzdv6NChlJkzZ86IESN416ZNmyhDU7Ru3bpRJjMzs0ePHi5zCDNMAaP8xo0bn3rqKdZCGqoaN25MAvnyyy8vXOieFIpTsICVlJSw5U9/+tOdd97JuzRBtzgq1NnlUYC+/NJ958ZqJwYOHEjNgDK7du26fPkyR5PaA7cKVjh5Fx9IFY4aNYotNBY988wzlHn66ae3bq2jJ+3WmfduiPMCZkgLHV51GeagX1xcHFGjZ0T/fn1oc+3an3mzR/eutDn0k8GGqUOKgDVt0ojzffv2os1du3aygPXp3fOLyZPIcvy4+z9zPQoYwZ9scZ7K0wjCeQHVTwW+mT6N8qSg7gv7eU12djZdxvDhn0SYAka7OL9wwQ+G9CWOVi2bb9686fr6gP/o0zcY5RZiRkYGCxjvzc3NFfkOHTqsWeO+5ywsSoZe77///gkmbFFuIZIQGu7H9F198MEHuTwXFuVFYRawyspKlymofCNdK3SLo0KdXR4FaPny5ZShOY27AblcQ4a4vztNmStXfnuWFbUcEWXee8NdIpOamjpx4sSOHTt2796dLcGmzrx3Q4IiYDojlAzoiT59g5E1hpEF7PTp0yL/4Ycf3lDAHnvsMbYwHj8DIzUSAiYXli0PPfQQqRfns7Kynn32WWvh+kW3OCrU2eW5TMQmhVgImFzm3LlzslHO1LKLXmkR36eP+6twS5Ys6dq1K+8KNnXmvRvS4AQMaI4+fYOpXcAMcxz58ssvf/zxR29DjMhs3bqVMtXV1Z9++ilbVq5c6TKXWYYnARs5cuTbb79NC7I2JmS5+eabR40atXbtWj58+/btlCkqKvrzn/+sXGS9o1scFers8i5cuOAyGTBgAN8l9ihgtPgmBfLYcmrZRa+dOnVq1aoV30yGgAFQz+jTN5gbCphh6gpZpk6dypvexhrDvB1E+XvvvTcuLo4tgwcP5r1WASNefPFF2vs///M/vGmYVRFt27pvoRvm52S0edttt505c0aU0QHd4qhQl5dHU5BnnnmGA/ef//yHjaJJEGSkTZqsCKPI1LJLzhDl5eUQMADqGX36BggE3eKYnJwY5f4jq2tf5tLt8kILfbwHAQN6oU/fAIGgWxxZwDgZ+l1eaKGP94IiYIcPH1q37trXC4PBoIH9un7cSbWGEQ35myb69A0QCEItNEmRFot6xcA2+njPeQETg6/jo/DkzydmnjypWm3g+JV4Izs7Gw/mCBB9+gYIBN3iKFZgB/a7P2jU7fJCC328FxQBE1/wJVJSkjmzbesWet286df4+Lg+vXuKH1d9Nm5MhPmjsdmzZtBmXl5ehPmMxPGfjeUD5ecicqKqVq9aSZaZM77t0rmj0KcpX3ze9ePOtCk/pV4cZdRU3rRJI66cn2TYv38f5afNzZp+2LNnN3qVjcyUKZM/bPQ+P5LRqKmhVcvmXIN8Lubrr6a2bNG0RfOmvPnjjwv4p2xxcQdoc8yYUVxYHNKxQ1vxu2y29+3j9pXYpPfbvFljymdmZjaKeI+uMzn5BO8ND/TpGyAQdIsjCdj+fTurq6t5U7fLCy308Z7zAlZefonG64iaBy9ZBezjLu5ncBg1o7Y8Osubbdu04h/6rV+/ji1iBSYEjOSBdx0+fMiwVCWw2rnyxh9+UFVVRZukZ8ePuX8KLRdLSDgsLAISMM60a/uRYT62Q67BugITZywpKZE3lTe7Zs2qNatXKfYDB/bz3iLzMSID+vflb5rNmztn27ato0eNyM8/bZg/Y+Ri4YE+fQMEgm5xLCm59vUNRrfLCy308Z7zAibG/bZtPzp//pxVwBb88D1blEG8e7cu4tmJxMyZ38XGRHOesQoYvxK0oCkuKurdqztv3lDAuHKxGR0VOXv2TM4zy5ctVSphhIDxc/SVGqwCZpjy88XkSeSW06fz+FEjAl5LMVQVvUHWKq72yy+niL3CKEPaSdc5dOh1dYY6+vQN/1iyeFFGRrpqbXhoHkfNL09z9PGe8wIWcf0T4mmQJVkyzOcwGaaAsT0jPZ2WL1yMV1pCz3JyfnsyoczMGd/yY+M9CphRcwg/jPG3w0w73zpQKu/WtUt0tPs/Mpo1/bC01L1CMswnUfGj7kmi8vJyhw0dsmvnDlGVImBKDRcuXOCVmUBcyVTzQLHJGVnA6N0pe8+ePXvqVDZldu7c7i4w87v58+YY5tOw6JLkNyUqCQM06RuyV1esWObRyTQ5s96/pZI7drjj5Sv8ZwhhgyZx9IZ/lzdoYL8I8zOCQQP723l8l9zBrZt+4LEdyhQUFIwdM0q1Oo1/3gsGzgvYyZMZHOP09DS20OBOm7NmzjBMASPVoU1ab/FeCuqE8eOojPiD4wH9+0aY/8jFmzItmjeJkD4DUwSMxJL0hp/EKB916dIlYaHK6Vyi8pEjhtOurVuuPdeZ+XzSBDJ+OdX9xxmUofFL7FIEzDBraBTxnqjhkyGD5LNv3ryJ9gpLfv5pyrdv15pbv9Kgv/vuG87IV0v5IYMH8iYt0WiTR7rCwsI2rd0fxclPVAsDNOkb4uawYYZDaVHML79sEPe3A8fjKUIXTeLoDf8ujwSM79vv2RNrJ14QsGDjvIDVDguYbAk8qAKKbmxM9IQJ4/r07qnu8xcSM9UEgokmfYNWt3yHYNu2ratWruCBY/asGbwI5k0hYLm5OW3btFqzxv0pZudO7r8yoJI8Y+OS1OwN83NQ+Y/oeBedKCsrU2wa5n8yGDXfD6JMh/buP/qhYhkZ6TQ/E9/xoRPxj1U+7tIxOirSMD/ZNcz/MDp27ChXVY9oEkdv+Hd5QsAM81YNvVIIFi1aePHiRQ6Kx5jSHHfO7FmUobksTbVTU1PZToGOjHR/JZI3Kb40ZxLxFXEXBaJr/pKXX6kx8FlkhIBFmF+m+/WXjfyNtgjzHznKy69N5fPycg3zOnnTV/zzXjCoawELNgkJhzk2IETRp2/Ig4V4peUvJVoZ02giC9iggf35KBYwZVw4fvzYhg3rxG1q5qNWzefPn3v6dB5vikNEhv9AlQYyeZHNf1AnF/vyyyksYHPnzubL69mzmyhfX+gTR4/4d3mygMnftRZBUWLapHGEYd4BogMNKWTt2n4kf9mYAs1fHSgruyiqEnG3frrPZ2GLAgsYtQdqDGzhQ/g73mKTapav01f8814wCDcBA6GOPn1j587tNHFu/VFL43oZE8gCNqbmvo1HASNyTp36ZMigli2aykbxBR/Dk4DNnPmdYQ5kvHnkSJL4Rzq5mBAwcc9TB/SJo0f8uzxZwH74fp5h/peh8n0uOaZ8e8kqYB6/sEbx5btTQsB4L83IxfRIPgv/3S5vCljAaMX/448L2OJRwIya67Q2VDv4571gAAEDeqFP3zAsonL82LFGEe+tWH7tOx00X44w12RWATt65Ajtiqq557NkySIam76ZPo33ijoXLvhh4cIf+Jsg48aO5kGH6p81cwZt8i8RxUBGo1K3rl3I3rdvL9pMT0+jGnr17D53ziwWMNrct2/v119NFYNsPaJVHK34d3mkQ5T4b2z5qzpTpkweOWK4+MdBJaaKgFHs6FiacLRv19owA00FInfv4kBTfH/9ZaOIr4i74f7TwWakVbTuF/cD6SxtWrfks/A6jxG3EEneJk74rGmTRlvMj+d79nD/4SKV5Ouk2vg6+T65r/jnvWAAAQN6oU/f8Ab/pM8OqakpIl9cXJyXp96xKS8v9/gzPpJGj8spj8avvpwiKqFptccydY/mcXTw8srLL12/6TmmgqtXr8qbaWm/FbZ+qVUgvhPH0FnEj7JpWiPvEnj8nqSYk93wOmvBQe8FCAQM6IU+fUNzunTuQLN1WnKJIUkrNI+j5pfnEzQ3Uk0WqJEsW/bTzz+v/vbb6eo+39HHexAwoBf69A0QCJrHUfPL0xx9vAcBA3qhT98AgaB5HDW/PM3Rx3sQMKAX+vQNEAiax1Hzy9McfbwHAQN6QX2jvLxMtYJQQ58xziOaX57m6OM9CBjQi5TkpBPH1V+3gNDi7NnTsTFbVatO0BB85cpl1QpsUF1dDQEDwDNVVVX6dA/gHxTB4uILqlUnck5lREdd9wRUYJN9e3ekpnh4UG29AAED2nGxtBgaFrpQ7E6duvZgbp05dvTghQuFqhXUSkz0lkOHYlVr/QEBAzpy4fxZmuipVqA9iQn7TmZ4/TWubpDWJicnqlbghfS0Ywfjr/uPxnoHAgY0hWbxNL5QOnQwJjFhr08pPi7SakQKMNXi1cOH93CwUkJND5KSDtBlx8ZsTbC8qXpMB+OjrMZ6TBxc3dTLgICB8EOrD5nDBlqpwKt1BlxtEwgYCDcO7N+NW0OOw3Nw8fw9EDyOHo3Xc7mjIRAwEFbw8ouTug/4Cy+/KNHkQN0HnAYN2D4QMBBWiM5vpk3qbuAXslfz83PU3cA5rm/A0LAbAAEDYYXS//FQD0fAqFo3UHOFq30CAgbCEPT8YACv1hlwtU0gYCAMQf8PBvBqnQFX2wQCBsIQ9P9gAK/WGXC1TSBgIAxB/w8G8GqdAVfbBAIGwhD0/2AAr9YZcLVNIGAgDEH/Dwbwap0BV9sEAgbCEPT/YACv1hlwtU0gYCAMQf8PBvBqnQFX2wQCBsIQ9P9gAK/WGXC1TSBgIAxB/w8G8GqdAVfbBAIGwhD0/2AAr9YZcLVNIGAgDEH/Dwbwap0BV9sEAgbCEPT/YACv1hlwtU0gYCAMQf8PBvBqnQFX2wQCBsIQ9P9gAK/WGXC1TSBgIAxB/w8G8GqdAVfbBAIGwhD0/2AAr9YZcLVNIGAgDEH/Dwbwap0BV9sEAgbCEPT/YACv1hlwtU0gYCAMQf8PBvBqnQFX2wQCBsIQ9P9gAK/WGXC1TSBgIAxB/w8G8GqdAVfbBAIGnOFMQS71Okqn87KLis4h5eZm7t2znRxSWlqsOss28XGRVAPVc/bsaespGlo6V1iQeTKFHLIndpvqKb+4fPkSN9rcnJNFFwqtZ0TilJ52jB2lerC+gYABZ6DGfelSmWpt8Jw/f4Y8k5eXpe6wwenT2SRdqhUYRsLhvY4MplTJmTN5qhV4gTTeEbc7CAQMOIBuzVo3/PBPWdlFP45qONACN0D/0DKuurpatYJaOX7sUEz0ZtVaf0DAQKBER20qyM9RreB6EhP2qqZaCXB0bghQq6uqqlKt9jhx4nBS4n7VCmyQlnrk0MFY1VpPQMBAoGCotYNPXjp9Onv/vp2qFVg4fvyQarIHhQPLL7/xqTEHFQgYCBR9WrPO+OQlWhzkY1Frg6jITarJHj6FAyjo4z0IGAiIsrJSfVqzzvjkpb17tp07d0a1Ags+eVXG7wOBoZP3IGAgICBgNvHJSxAwm/jkVRm/DwSGTt6DgIGAgIDZxCcvQcBs4pNXZfw+EBg6eQ8CBgICAmYTn7wEAbOJT16V8ftAYOjkPQgYCAj9BWz69OkTJkxQrXWOT16CgNnEJ6/K+H1g/bJ27dply5ap1jpHH+9BwEBA1L2AuVyunTt3qlbT3qhRI9VqGI8++ijtUq11jk9e8knAJk+eTG8wMzOTN3/99dexY8deX8QDd9xxh2q6HpfEkSNH1N1+kZiYuHv3btUaAD55VcbvAx2EHPvss8+qVomEhIR33nlHtnTq1Klp06aypV7QwXsMBAwERFAFrKCg4KuvvpItzzzzzJ133qkI0rx584waAdttwvaUlBTKHz16VFhWm4gDS0pKpk2blp+fz5sxMTH0Skrg7CDL+OQlPwRM+EQWsOPHj8+aNevKlSuiME3hSUUMScDIyeSE0tJSUYZRnJyamircEhkZefLkScqwZcaMGVSJKHngwIHFixeLX1lxGTovvb7yyitUrajn6tWr3kraxCevyvh9oIN4FLAdO3asW7eO87KAsXNyc3PZ8/WLDt5jIGAgIIInYA899NC1+b/LJTSG8tu2baPXvXvdD7agsU+UcZkCtmDBAlfNyMuWNm3asIXLkP4999xztFlRUSEOpHGBLPfff//f//532gzGLUefvOSHgD399NNvvfWWIQkYZcQb5JKjRo3izZdffpkFrLy8XJRRftgrjpItOTk5eXl5Ypc4VlhGjBihWORNOb9y5UqxyaMzZfr27ct7beKTV2X8PtBBXBYBEw6hxm9IAkbB+u677yhD0xE7y+tgo4P3GAgYCIjgCRh14+Ji93PcKUMzd8PsvTy60SuPv0888YQY71w1txApQ/N6ztAALQsYz15Zn0jG9u93P0yoqKjolltuMUwBe//997k2x/HJS34ImGG+QVr9CAETnpk0adLQoUNly+DBg9mBt99+O6+96MAXXniB9zIuCbbQgpU3Sf9EGc4MGTKkS5cusoVG3o0bN7JFrM/ee+89UYAy06dPp0zjxo3ZSK+PPPII77WJT16V8ftAB3F5EjCRKSwsZAFr3ry5sEPAFCBgICCCKmBWi0xSUhK9vvrqq2IvCxj1cMr/+c9//utf/0qbQsDOnz///PPP87FcXq7ZMAVMWBzHJy/5J2C0KqVMs2bNFAErKysjuaqqqhKWq1evsoC5zOWm4FqNJrJ/ZCMhnkAoV+gy13DCsnnzZjGfYIshCRiXVE7tku4u2sQnr8r4faCDuK4XsOjoaF5D866pU6eSgD322GOUnzlzJtshYAoQMBAQQRWw1NRUzrz++uuckfeS3pBEsZGWES7pSxwuk7w89z9lCAETHyfw5osvvshf6KKz8Gge6gJG/Pe//6W8ELDLly9TpmvXrp9++ilbuFi7du3ECuzChQuGeUOV6uG9jOxtZteuXffdd9+tt9560003scVVc+ORKuzcuTNbeNczzzxDGiZbCAqQ2KQMLQ0N89MdCJiwiMy5c+cSExMpoHJ8IWAKEDAQEMETsDfeeMNVAw3EKSkp99xzj9g7cOBAV82UnyF9EgImf9FD+QyMuOuuu3iXsPDXHMJAwAzzTfEYd+LECfEGedfEiRN5k3zLAkZvXJTJzs4WlXA9gq1bt4oFHGdYt+QyfNSqVasUi8gY5tdkxK4NGzaIkkJxG5qAycgWCpAhfQb2r3/968EHHzQgYBYgYCAggidgYYZPXvJJwOoRHnbrEZ+8KuP3gcDQyXsQMBAQEDCb+OQlCJhNfPKqjN8HAkMn70HAQEBAwGzik5dCRcDqHZ+8KuP3gcDQyXsQMBAQEDCb+OQlCJhNfPKqjN8HAkMn70HAQEBAwGzik5cgYDbxyasyfh8IDJ28BwEDAQEBs4lPXoKA2cQnr8r4fSAwdPIeBAwEBATMJj55CQJmE5+8KuP3gcDQyXsQMBAQAQrY8WPHIiN9++mPlUED+6km/fDJS04JWELCYZHPzc3h3yzXGV0/7qSanMYnr8r4fWDt5OXlnT9/TrWGHUHynh9AwEBABCJg3bt1mTt39qqVKyI+eFfd54m2bT9STSb8wI4A8Va5N7uv+OQlpwRMduyc2bN2794l7fRM649aqCYbePTSiRPHVZPT+ORVGb8PrJ0ffpi/besW1eojNrtDPRIk7/kBBAwEhN8C1qlju5SUZMW4cMEPvXv3oA581PwDKspw+nLqF2Jz2NAhaWmplOnZo+uiHxeSnYeMzZt+nTnjWxJF0f8p07dvr+bNGvPmtm1bySKftFHEez17dmvW9EOqkysnI1dOiSsXJ83MzOTyycknRA328clLQRWwoZ8MprdMuy6cP89l+vfrwyXFmxVHdWjftkvnjh82ep9C06RxBO0tLioiO1logUUWysvemzJlMhej/OpVKw33Y4L3d+ncgSyjRrkfZ0WnZp+LUwSCT16V8fvA2lEE7MqVK/ROW7Vs3vVj93O2DNPDLZo33bx5EzlBFOvRvSt1B3Yme5IduG/fXnI+tbqff3b/BxAZBw3sP2bMqEuXLlGeQjBk8EDDbPm0SU5esngRRyfCbPlcSTAIkvf8AAIGAsJvAfPYu4SRM8qmmOYnJ18TIbYLAfv6q6mU+XzShMOHDw3o3/fMGbcGzJs7h6SLMhMnfMZHCfLzTxs199m8VS7so0eN4PL+Lfh88pKDAiYnErDi4mLSeLHXcM8k2hvuh0mWsFFZgZGAVVRUGDWFY2Nj5s6ZRZmdO7dzAfa58BIJmPhbFhYwEUTWRd6U720Ggk9elfH7wNpRBKzxhx9wZvxn7uc/kZfy8tx/3LNmzSpZwISL+CnJSrMXGXrNyEinTE5ODv+HgLCLYixg3PINc9LGGWcJkvf8AAIGAsJBAcvKyiSR4Ly1ZxrSKEm9lNZVETUTVSFgPGLOnzcnLu4A7+VEkma4/99SXfC1aN6E9o4a6V4ZeKtc2Glw4fJidPAJn7zkoICJPK/ANm5Yv2rlCnnvuLGjKSPWqVYB4wwXPnQwnurhTU5t27Qyrhewa0fWCJiy2KL5hPB54PjkVRm/D6wdRcCE/8lv8ibNCWQB27F9m2hvcjHhOl5pCTs1RXK4OETI5OBBA6j1Zmdliehwy3ecIHnPDyBgICD8FjBD6pCbN29KT08TlrKyMs4oXbpnj67UOa12jwI2c+Z3lKHNLyZP2rVzh2ERsMLCs7xW6N+vj2Gp/OjRI9aTcnlxdp/wyUvBEzB6C2zMSE9v2sT97GNSFMPt84vWQwzvAjZ82Cds/2b6NMP0Em9aBUwOFvm8X9/ehulzXosEiE9elfH7wNpRBKxb12uLXZYiaqL0xkl+aJYgC9iHja79Cx11BMPSvEVGbLZq2byysrKkpIQtdDg1eMo0aRzBKzBu+QS3fMcJkvf8AAIGAiIQASNoDI2o+XTEMO+N0GaP7l2pfxqWDmyYfZXWCocOHYwwFw1s9yhglJn8+UQqsGTxIj7WugJr07plRM0HbEbNOMKVR0buVk5aWFjI5fnR9b7ik5eCJ2CUiY87QG6n2TrbR44Yzs7kzVkzZ4i84V3AyMnyUaKAVcDIXVzyzBn331rSmkD2eYD45FUZvw+sHRKwiJrVD7c3cnWjiPe2bnH/swyxfv26cePG0DSiT++e4qjv58/jQ3gzKyuT8+Xl5ZShVsffbBQFCgoKqE3yUWyZMH7ciBHDhg4dzLcWueW3b9ea9zpOkLznBxAwEBABCljDwScvOSVgYY9PXpXx+8BAaNWyGf/JOOncpk2/qLv9RciYyASbevGeRyBgICAgYDbxyUsQMJv45FUZvw8MEFqPOvUFFpm0tNRgVOuN+vKeFQgYCAgImE188hIEzCY+eVXG7wOBoZP3IGAgICBgNvHJSxAwm/jkVRm/DwSGTt6DgIGAuHz5kj6tWWd88tL+fbvOnslTrcCCT16V8ftAYOjkPQgYCBR9WrPO+OSlo0fiM0+q35kEVqKj3N879wOfwgEU9PEeBAwEij6tWWd88lJpaZFP5Rssp05lqCZ7kHvLytzfOAe+UllZqU/jhICBQMHHYDckKXF/dbX7KUH22bd3Bx2lWoFEgK0uwMMbLOS3qir3zzR1AAIGHODokbiSkjr9q44Q4vTpbP/GSv+OaiDsid1KrU61+sKZM3m4T+sr1Cazs9wPzdEECBhwBmrZR5ICGlDCkvi4qEB0iI4tyM9RrQ0ecsvhw3tUq+9QPQf27+JH6ILaqa6uPhgfnZKcqO6oVyBgwElyTmXQoIDEKSnJ/USrAKmqqqR6rJU32JTj7+de3jh79rT1LEhKytdyIgUBA+FGZWVFVACLHgDqnSj350xYF94YCBgIN2JjtlL/T0zYq+4AIBQ4GB9NDXjvnmv/uAZqAQIGwoqszFRx06OoyP0MbwBCiMLCfNGAc3NOqrvB9UDAQFih3LhXdwOgN2jAPgEBA2GF0v+xCAMhhLz8goDZAQIGwhD0fBDSoAHbBAIGwhD0fxDSoAHbBAIGwhD0fxDSoAHbBAIGwhD0fxDSoAHbBAIGwhD0fxDSoAHbBAIGwhD0fxDSoAHbBAIGwhD0fxDSoAHbBAIGwhD0fxDSoAHbBAIGwhD0fxDSoAHbBAIGwhD0fxDSoAHbBAIGwhD0fxDSoAHbBAIGwhD0fxDSoAHbBAIGwhD0fxDSoAHbBAIGwhD0fxDSoAHbBAIGwhD0fxDSoAHbBAIGwhD0fxDSoAHbBAIGwhD0fxDSoAHbBAIGwhD0fxDSoAHbBAIGwhD0fxDSoAHbBAIGwhD0fxDSoAHbBAIGwhD0fxDSoAHbBAIGHOby5UtFRefqN1H/txrrOF25cll1DdCVq1cuFxWdtwaxvpIODVhOqr+0AQIGnOHE8cPU606cSFB3NGAKCnLJJzmnMtQdQA/yT5+iACUm7FN3gOupqLh65EichutCCBhwgLKyi9FRm1UrMKFuHx8XqVpBfVNdXU2hoVd1B/AOeayyskK11h8QMOAAGk7NtAL+0RAExQ9yck5q5TcIGAgUatAlJUWqFVxPdNQm1QTqj317d6SlHVWtwAa5uZn6aBgEDASKPq1ZZ+AlrUA4AkEf70HAQEBUVFzVpzXrDLykFQhHIOjjPQgYCIiyslJ9WrPOwEtagXAEgj7eg4CBgICA2QRe0gqEIxD08R4EDAQEBMwmIeqlJYsXlZVdVK2hT4iGQxP08R4EDAQEBMwmmnvpl182qCaThITDV69eVa03oqCgYOyYUapVJzQPh+bo4z0IGAgI/QVswoQJqqk+qBcvtW370ZQvPud8cVFR//59fv1lI28u+OH7eXPndOzQlvLp6WndunYZNnQIZWhzzOiRvXt1P3Uqm/JkpNdJE8cXFRX17t0jLy+PD//hh/mtWjbbuXM75QsLz0bu3jVoYD/eZUgCppz04sWLffv2+vqrqVwt0alj+wnjx4kD64x6CUfYoI/3IGAgIJwVsKSkJJfJLbfcou6rlZiYGNVUA9WmmuoDB71kk4gP3qXXxMSExh9+UFVVxZtffTnlp58WU6ZRxHu0tCJFmTN7liGtwDIy0qlwRUUFl+fXDu3bkqqJTSoQHR1FmSlTJhvuHwbltG3TikSLazBqBMx6UtokSSsvv8T2zZvcPikpKWn9UQtxbN3gSDjGjBnDzfXNN99U93mBy2dmZqo7fGT27Nlywz569Chv0utbb731W7ng4Ij3HAECBgLCQQF79NFHRZ+Mi4sT+erq6sWLFx84cIA3c3JyKisrExMTv/nmG7bs3r377rvvplfezMrK+uqrrzjPez0eRZSWlk6bNk2MvKyCNLjwIZs2bZo3b54oHCBOeckm2VlZo0eNEJuTJk1ITj7BeRaP5s0a8yavnORbiFSAkyhMAiZ20evnkyaIMnQiErAx198wZAGznnT5sqXyJmcoJSUm8madEXg4mjVrds8993A+IiKCmiu9a2pR3HioXfGuGTNmnDjhdsKFCxdmzpxJxURDFbsMs+2lp6dv2bJl2bJlbCHOnz8vb8qwELZq1Yo3PQrY8ePHRa+hk5aXl4v8yZMnOe8fgXvPKSBg4P+1d74/UV1pHP8DMMYYY3yl0cRXxhDfaUw0vvAdEUERkSpdF5VRFtuq5UdRQKssG7u0pUTNprsVkS6rs5ZqVymKa7Q/toiVRtgIq2UVdYqgg4zIUOXuc+dhzl7vBTu95zBzr34/ubl5znN+DHnOOfO9Z2Y4RwqFAkZzr6SkxOwNz1Viz549lKysrExISGDP9u3bjQW0sAouXLiQk5w7ai1jRdaw6dOnz58/n5KlpaUzZswgY/bs2VOmTOHCkqiKUoTQ6mdVSjLbNUerjx/7W3V1FSdfLGAkTsZiowrY373HOcmMJWDWF/VkbTAmBaZkFJDvDjHAjLS0tJCfHqc4l+7z5s2j+5w5c0g2xHgzZWmhsUfLOM6dOnUqeTIyMsiePHky3enZy/gqVVVV5MzOzuamtNEEbMKECdya8Kek6D1+9+5dUcs28tFTBQQMSKFKwGjdQ/PK5/OZ/F6vNykpiW2eeCRFiYmJZAwMDIipSPOfDdKemzf13d8p69w5/RuasWotXrz46tWr7KHZzo0sX76c26EyR44c4QbZI4mSKP0qNm5YX19/xpO1sez3+7SQSBw6eIDuP/6ox8ckYI8fB4p2Fba1tdafOX36H1+8u6fkzTdzuJZmETBi3dr0pqbv+KO/sQSMyxtf9HfZHrJJWbmdmppq0sKPKj6kP9VYPQrId4cYe83NzaUhGhoaWMDKysrIT6rDg6e9vZ0L0zKLDWsWjT02ysvL2aAC58+f5xfavXs3vxZDniVLlgwPD5PBZUwCRrNG/HlkFBQU5Ofnsyc+Pn7atGn/b8sW8tFTBQQMSKFKwLTQTCsufu59kFi2bBlPUc0gRUJUxCwVAhYXgnSI7tXV1S+oFRdaaQmMjWiht5ilS5dya8Ipg6oouZrCwnw2or/kMiHfHWJg0JqGV1d5eXksYOznR6VFixYVFRWxUwiYNUsIWGNjIxu0DiMjJyeH7h6Ph9skamtreVgKNIuA0azhJHv4UwQy9u/fL/wyyEdPFRAwIIVCAZs7d66YXfyOQEZdXd2CBQvYyR6rFBGTJk0Snp9/1o97iPslAaMV2MWL+i8RtPAyyyhgCQkJbFDhYDAo/LZRFSVX897+PySHvvQyfSYWfeS7IzMzkxbugYD+T3IsSCYB27t3L9uHDx9mQwiYNcsqYHQnmw2jgFFSfPf28OFDLmwSMJo1ZAwO6keqkrFz504ycnNz40KfioumbCMfPVVAwIAUCgWMmDlzZlyYmpoadgrPyZMntdGkSJShAqJw3C8JmKhFNDQ0aM8L2MSJE0WucMqgMEpAHiXdIUYI09nZaRSw3t5e9sfHx7NTCJg1a1QBY0hyTAJm/M0tJUlErd+BzZo1i6vTSDYWtn5KbwMl0VMCBAxIoVbAXmIQpdhy/fpzP3R8BbvD+J2xJM6JHgQMSAEBixBEKbaQgFEXXGm+xMlXsDtotefSn9S+AAgYkAICFiGIUmxhAeOrp8eH7pDBOdGDgAEpIGARQlHy+3txxeq6dq1JCFjTd+cxaGVwTvQgYEAKCFiEIEqxRazAfvrpjobukMM50YOAASkgYBGCKMUWErB79/TtiRl0hwzOiR4EDEgBAYsQRMlRoDtkcE70IGBACnsC1tHR0dbWKpKBQOD+/fuG/NFJTlrW2KjvDiXDoYMHzK6oYCNKYPxQ3h0tLfq2ZGopLtb/AZnvjkJ59GwDAQNS2BOwt3e8ZdxMaLNnU91nJwz5o0PvEQ8fPNDkNiLKy91hdkUFG1EC44fy7pAZk2PBbUbYcjSPpFEePdtAwIAUdgVs2+XLTWWhjc+DweCWzZvq6j5je3XqytfS0zxZG7XQcVPl5e+tW5vOc5i3fK05Ws3bEZFddfiTlSuWb8hc33rtGpcXG8WS35O1QezIXn/m9NrX0ijLJGDk2fbWG+lrUjnpPX6Mi4lcuujvYU9nZ+eK5ESyxSkhkWMjSmD8UN4dJpnRx9W2N4Rzy+asrVuz01anmIqlrEzatPG35Hz27Jm1Fht8p/lCBjVSW/upyKWJI8rQxceEFuTnciP8tEcvSrOgvf0611KC8ujZBgIGpLAtYFp4ZtKs6/P7eQVG85kL7Nurn5xCgnT2rL7J029eX/v06VOxZ7lphguDyg8PD7OHDwsmPnj/j9aSjN/v9/nuGZ0NX9azQe8CRv+JE166lxTv4vIdHR3sjxwbUQLjh/LuMI6rvr4+FiTi321tt2/fytqUaS32yV8+5uF95Uqz13vMVEsUNt6FQXU5SXXZ4BUYNUKqZixJdzEpVKE8eraBgAEp7AqYfoQH703O04wFTMzS70PTkgSJnxxpkUSLM6uAiTMbhYBxkj18vZ6hH/onlmI7tusvLdias4WLGZ2a5V2D9/Ol95c1aatobdfd3W0sHAk2ogTGD+XdYRxCX5zSN+1kKisrTp363HqSJ8EjU2CqpVkETFyapa4WFjBqxHv8GHtMY1ghyqNnGwgYkEJGwIj16zPu3OnSwgK22TPy8Lg6daUWgYCZDKOAFb4zcnLHRxX62biiJLfMlO57l39LInL5ECxNP7L9oNHPJzEmhx9mbbwp2IgSGD+Ud4dxSNAguXRJP+jg5o0b/f2PRG7tXz81Frtw4Z883ioqPjj5ed1YtcR9YGBAJKnukyd6kupya+ynRtigRlJXrRB+tSiPnm0gYEAKSQETs0v8iINm3YrkRP4obywBa2w8RxUpq6uri7+y4uM5jAL254//RH5xbGNfXx8li4t21hzVt6hnqNaatFTyi7/H57tHVYTIUVZBQS7dKz58n5I9PT0Z69JpBWbjgBUbUQLjh/LuSA4vj3jIFe0qJDv37ZGzvwOBwDsFeTRcTXJCz0nk4RNHNUstLsx3GnLZW/TjQHt7ezmXnvaMdQ8dPMAv3Rz6tszUiFqUR882EDAghT0BcwsKJ/9LHCU3Es3u6Oho50/LxfLI7UQzei8GAgakeLkFTCGIkqOIfne0tFzt7+83e91J9KM3FhAwIAUELEIQJUeB7pDBOdGDgAEpIGARgig5CnSHDM6JHgQMSDE0FHTOaHYyiJKjQHfI4JzoQcCALM4ZzU4GUXIU6A4ZnBM9CBiQhUbz8PDIDgJgLJwz5wHx1aX6+936pirg19Lf3+ecwQwBA/IMO2dAO5Nvvj5rdoFYg0Frg6HgoKPiBgEDCrh160Zr68iebMDE5aYLjprzgHn8OPDtN7Kn87xq0Ej2+x+YvbEDAgbUcDF0XrvPp+8LBZjBwSccFnMGcAZff9VAvXPrv/8xZwALXbdvUqy6u++aM2IKBAyo5NEj/w8t3+Liixam5gAB5zE0FLT2Ha7nr3/x1otOAwIGAADAlUDAAAAAuBIIGAAAAFcCAQMAAOBKIGAAAABcCQQMAACAK4GAAQAAcCUQMAAAAK4EAgYAAMCVQMAAAAC4EggYAAAAVwIBAwAA4EogYAAAAFwJBAwAAIArgYABAABwJRAwAAAArgQCBgAAwJVAwAAAALgSCBgAAABXAgEDAADgSiBgAAAAXAkEDAAAgCuBgAEAAHAl/wN20M10g8bCiAAAAABJRU5ErkJggg==>