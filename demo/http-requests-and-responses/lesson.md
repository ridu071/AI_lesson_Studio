# HTTP Requests and Responses

*Level: beginner - Duration: 45 minutes (mandatory content) - Version 1*

## Learning objectives

- **LO-01** Explain GET and POST methods *(understand)*
- **LO-02** Distinguish between 2xx, 4xx, and 5xx response status categories *(understand)*

## Intro and goal  *(4 min)*

**Every time you load a webpage, your browser talks to a web server using HTTP messages.**

**Example:** Imagine typing a web address into your browser and pressing enter. Behind the scenes, your browser sends a request, and the server replies with the page you wanted.

*Visual (flowchart): The basic client-server transaction cycle in HTTP.*

- Client Browser
- HTTP Request
- Web Server
- HTTP Response
- Client Browser -> HTTP Request: sends
- HTTP Request -> Web Server: reaches
- Web Server -> HTTP Response: returns
- HTTP Response -> Client Browser: delivers

- Explain GET and POST methods
- Distinguish between 2xx, 4xx, and 5xx response status categories

## Overview of HTTP Protocol  *(3 min)*

**HTTP is a stateless request-response protocol running in a client-server model.**

**Definition:** Protocol: A set of rules defining how messages are formatted and exchanged between computers.

**Definition:** Client: The user agent, such as a web browser, that initiates requests.

**Definition:** Server: The host system that receives requests, processes them, and returns responses.

**Definition:** Stateless Protocol: A protocol where the server does not retain status information about each user across multiple requests.

*Visual (concept map): Core relationships within the HTTP architecture.*

- HTTP Protocol
- Client
- Server
- Request
- Response
- HTTP Protocol -> Client: uses
- HTTP Protocol -> Server: uses
- Client -> Request: sends
- Server -> Response: returns

## Core idea 1: Understanding GET and POST Methods  *(8 min)*

**Methods classify the desired action a client wants to perform on a resource.**

*Visual (table): Comparison of GET and POST characteristics.*

| Method | Primary Purpose | Cacheable? |
|---|---|---|
| GET | Retrieve a resource | Yes |
| POST | Submit data for processing | Yes |

A request method is a verb in the start line of an HTTP request. GET is a safe method meant for read-only access. POST is used when you need to send data to the server.

**Example:** Using GET is like reading a book from a library shelf. Using POST is like filling out a paper form and handing it to the librarian to create a new library card.

*Visual (analogy scene): Analogy linking real-world actions to HTTP methods.*

- Library Shelf
- GET Request
- Submission Form
- POST Request
- Library Shelf -> GET Request: matches read-only action
- Submission Form -> POST Request: matches data submission action

**Q1. What term describes a request method like GET that has no intended effect on the server state?**

*Hint:* Think about whether safe methods modify server data.

## Core idea 2: Response Status Categories (2xx, 4xx, 5xx)  *(8 min)*

**HTTP response status codes tell the client whether a request succeeded or failed, and who is responsible.**

*Visual (labeled diagram): The major response code categories.*

- Status Code Categories
- 2xx Success
- 4xx Client Error
- 5xx Server Error
- Status Code Categories -> 2xx Success: includes
- Status Code Categories -> 4xx Client Error: includes
- Status Code Categories -> 5xx Server Error: includes

A 2xx status indicates that the client request was successfully received, understood, and accepted. A 4xx status indicates an error caused by the client. A 5xx status indicates the server encountered an error.

**Example:** If you misspell a URL and get a 404, the client request had a problem. If the website crashes because its database is down, it returns a 500 server error.

*Visual (table): Breakdown of HTTP response status categories.*

| Category | Meaning | Responsible Party |
|---|---|---|
| 2xx | Success | None |
| 4xx | Client Error | Client |
| 5xx | Server Error | Server |

**Q2. Which HTTP status code category indicates an error caused by the client?**

*Hint:* Look for the category starting with number 4.

## Worked example: Analyzing an HTTP Transaction  *(7 min)*

**Tracing a request and response reveals how methods and status codes work together.**

*Visual (code snippet): Sample HTTP request and response start lines.*

```

```

- Request Line
- Response Line

- Step 1: Client prepares a GET request for /customer/123. (Why: Retrieves a specific resource safely.)
- Step 2: Client sends the request over the established connection. (Why: Transmits the action verb and URI to the server.)
- Step 3: Server receives and processes the request. (Why: Determines if the resource exists and if the user is authorized.)
- Step 4: Server returns a response starting with HTTP/1.1 200 OK. (Why: Indicates success and that the requested resource entity is attached.)
- Step 5: If the server encountered a bug, it would return a 5xx status instead. (Why: Signals that the server failed to fulfill a valid request.)

*Visual (flowchart): Flow of the worked example transaction.*

- GET /customer/123
- Server Processing
- 200 OK Response
- GET /customer/123 -> Server Processing: triggers
- Server Processing -> 200 OK Response: produces

### Practice: Try it: Identify Method and Status Category (2 min)

Review a scenario where a client submits user profile updates using POST and receives a 500 error response. State which method was used and which status code category the error belongs to.

*Hint:* Recall that sending new data uses POST, and 5xx codes indicate server-side issues.

## Test  *(10 min)*

This test consists of 10 questions covering GET/POST methods and status code categories. A hint is available for each question, and answers appear only after submission.

*Visual (table): Test coverage overview.*

| Objective | Tested Concepts | Question Count |
|---|---|---|
| LO-01 | GET and POST methods | 5 |
| LO-02 | Status code categories (2xx, 4xx, 5xx) | 5 |

**Q3. Which HTTP method is defined as safe and intended for read-only resource retrieval?**

- POST
- GET
- PUT
- DELETE

*Hint:* Think about retrieving versus submitting data.

**Q4. What is the primary purpose of the POST method in HTTP?**

- To delete existing server resources
- To submit data for server processing
- To retrieve a read-only document
- To check if a connection is alive

*Hint:* POST is associated with sending form data.

**Q5. Which response status category signifies that a request was successful?**

- 1xx
- 2xx
- 4xx
- 5xx

*Hint:* Think of the category that includes 200 OK.

**Q6. An error status code caused by the client falls under which category?**

- 2xx
- 3xx
- 4xx
- 5xx

*Hint:* Review who is responsible for 4xx errors.

**Q7. If a web server encounters an internal error and cannot fulfill a valid request, what status category is returned?**

- 2xx
- 3xx
- 4xx
- 5xx

*Hint:* Server faults are represented in the 5xx range.

**Q8. A user tries to fetch a product catalog page using a safe, cacheable method. Which method did they use?**

- POST
- GET
- PUT
- CONNECT

*Hint:* Look for the method defined as safe and read-only.

**Q9. An application submits new user registration details to a web server. Which HTTP method is appropriate here?**

- GET
- POST
- TRACE
- OPTIONS

*Hint:* Registration sends new data to the server.

**Q10. A client requests a file, but the URL contains a typo resulting in a 404 Not Found. Who is responsible for this error?**

- The client
- The server
- The proxy cache
- The transport layer

*Hint:* Review the responsibility definition for 4xx status codes.

**Q11. Order the steps of a basic HTTP request-response transaction.**

*Visual (flowchart): Transaction flow order.*

- Client sends HTTP request message
- Server processes request
- Server returns HTTP response message
- Client sends HTTP request message -> Server processes request
- Server processes request -> Server returns HTTP response message

- Client sends HTTP request message
- Server processes request
- Server returns HTTP response message

*Hint:* Think about who initiates the transaction.

**Q12. Match each HTTP status category to its description.**

- 2xx = ____
- 4xx = ____
- 5xx = ____

*Hint:* Match category numbers to their outcome definitions.

## Recap  *(5 min)*

**You now understand how HTTP requests use methods like GET and POST, and how responses categorize outcomes using 2xx, 4xx, and 5xx codes.**

- HTTP is a stateless request-response protocol between clients and servers.
- GET requests are safe, read-only operations used to retrieve resources.
- POST requests submit data to the server for processing.
- 2xx codes denote success, 4xx client errors, and 5xx server errors.

*Visual (table): Cheat-sheet table for HTTP methods and response codes.*

| Concept | Key Summary |
|---|---|
| GET | Safe, read-only retrieval |
| POST | Submits data for action |
| 2xx | Successful request |
| 4xx | Client-side error |
| 5xx | Server-side error |

**Next steps:**

- Explore browser developer tools to inspect live HTTP traffic.
- Read about additional HTTP methods like PUT and DELETE.

## Answer key

1. (check, understand) **safe** - GET is defined as a safe method meant for read-only access.
2. (check, understand) **4xx** - 4xx status codes are designated for client-side errors.
3. (test, understand) **GET** - GET is a safe, read-only method.
   - Wrong: "POST" (M1) - Confusing data submission with safe retrieval.
   - Wrong: "PUT" (M2) - Assuming updating methods are read-only.
   - Wrong: "DELETE" (M3) - Confusing deletion with reading.
   - Review: SEC-03
4. (test, understand) **To submit data for server processing** - POST is used to send data to the server.
   - Wrong: "To delete existing server resources" (M4) - Confusing POST with DELETE.
   - Wrong: "To retrieve a read-only document" (M5) - Confusing POST with GET.
   - Wrong: "To check if a connection is alive" (M6) - Confusing POST with connection checks.
   - Review: SEC-03
5. (test, understand) **2xx** - 2xx status codes indicate success.
   - Wrong: "1xx" (M7) - Confusing informational status with success.
   - Wrong: "4xx" (M8) - Confusing client error with success.
   - Wrong: "5xx" (M9) - Confusing server error with success.
   - Review: SEC-04
6. (test, understand) **4xx** - 4xx codes indicate client-caused errors.
   - Wrong: "2xx" (M10) - Confusing success with client errors.
   - Wrong: "3xx" (M11) - Confusing redirection with client errors.
   - Wrong: "5xx" (M12) - Confusing server errors with client errors.
   - Review: SEC-04
7. (test, understand) **5xx** - 5xx codes indicate server-side errors.
   - Wrong: "2xx" (M13) - Thinking server crashes return success.
   - Wrong: "3xx" (M14) - Thinking server errors are redirections.
   - Wrong: "4xx" (M15) - Confusing server errors with client errors.
   - Review: SEC-04
8. (test, apply) **GET** - GET is safe and cacheable for fetching resources.
   - Wrong: "POST" (M16) - Assuming catalog fetches require POST.
   - Wrong: "PUT" (M17) - Confusing PUT with retrieval.
   - Wrong: "CONNECT" (M18) - Confusing tunneling with resource fetching.
   - Review: SEC-03
9. (test, apply) **POST** - POST is used for submitting data to be processed.
   - Wrong: "GET" (M19) - Using GET for data submission.
   - Wrong: "TRACE" (M20) - Confusing diagnostics with submission.
   - Wrong: "OPTIONS" (M21) - Confusing capability queries with submission.
   - Review: SEC-03
10. (test, apply) **The client** - 4xx errors are caused by the client request.
   - Wrong: "The server" (M22) - Assuming all errors are server faults.
   - Wrong: "The proxy cache" (M23) - Blaming intermediate caches for URL typos.
   - Wrong: "The transport layer" (M24) - Confusing application status with transport protocols.
   - Review: SEC-04
11. (test, apply) **Client sends HTTP request message -> Server processes request -> Server returns HTTP response message** - Transactions follow client request, server processing, and server response.
12. (test, transfer) **2xx = Success; 4xx = Client error; 5xx = Server error** - 2xx is success, 4xx is client error, 5xx is server error.

## Review material (shown when a learner scores below 70% on an objective)

### LO-01: GET retrieves data safely, while POST submits new data.

*Visual (analogy scene): Remedial view of HTTP methods.*

- Catalog Lookup
- GET
- Order Form Submission
- POST
- Catalog Lookup -> GET: read-only
- Order Form Submission -> POST: writes data

Think of GET as asking to view information without changing anything.
Think of POST as sending new information to be recorded or processed.

- **Mix-up:** Believing GET can be used to submit large forms. **Correction:** GET is for retrieving resources; POST is designed for submission.

### LO-02: Status code ranges indicate who encountered or caused the issue.

*Visual (table): Remedial breakdown of status ranges.*

| Range | Target |
|---|---|
| 2xx | All good |
| 4xx | User fault |
| 5xx | System fault |

2xx means everything worked as expected.
4xx means the client made a mistake in the request.
5xx means the server failed to complete a valid request.

- **Mix-up:** Thinking 5xx errors are caused by user typos. **Correction:** Typos cause 4xx errors; 5xx errors mean the server itself crashed or failed.

## Practice answers

- **Try it: Identify Method and Status Category:** Method: POST. Status category: 5xx server error.

## Supplementary videos (optional, not part of the 45 minutes)

- [The Http and the Web | Http Explained | Request-Response Cycle](https://www.youtube.com/watch?v=eesqK59rhGA) (9 min)
- [31 HTTP Request Response structure](https://www.youtube.com/watch?v=rZNdo9UjF94) (14 min)
- [HTTP crash course | http Methods | http headers](https://www.youtube.com/watch?v=qgZiUvV41TI) (24 min)

## References

- [HTTP (Wikipedia)](https://en.wikipedia.org/wiki/HTTP) - retrieved 2026-11-07
- [List of HTTP status codes (Wikipedia)](https://en.wikipedia.org/wiki/List_of_HTTP_status_codes) - retrieved 2026-11-07

**Further reading (books; content not reviewed by the tool)**

- [HTTP (1997)](https://openlibrary.org/works/OL16026044W) - David Gourley, Brian Totty, Linda Mui
- [JavaScript (1996)](https://openlibrary.org/works/OL1643770W) - David Flanagan
- [Het Achterhuis (1944)](https://openlibrary.org/works/OL266178W) - Anne Frank

**Videos**

- [The Http and the Web | Http Explained | Request-Response Cycle](https://www.youtube.com/watch?v=eesqK59rhGA) - The TechCave
- [31 HTTP Request Response structure](https://www.youtube.com/watch?v=rZNdo9UjF94) - Chai aur Code
- [HTTP crash course | http Methods | http headers](https://www.youtube.com/watch?v=qgZiUvV41TI) - Chai aur Code

