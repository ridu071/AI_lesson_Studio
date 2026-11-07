# HTTP Requests and Responses

*Level: beginner - Duration: 42 minutes (mandatory content) - Version 2*

## Learning objectives

- **LO-01** Explain GET and POST methods. *(understand)*
- **LO-02** Distinguish between 2xx, 4xx, and 5xx response status categories. *(analyze)*

## Introduction to HTTP Protocols  *(5 min)*

HTTP is a request-response protocol in the client-server model. A transaction starts with a client submitting a request to the server, and the server returns a response describing the disposition of the request.

## Understanding GET and POST Methods  *(8 min)*

**Definition:** A request identifies a method to classify the desired action to be performed on a resource.

The GET method requests a representation of a resource. The server should only retrieve data and not modify state. GET is preferred over POST for retrieving without making changes because it can be addressed through a URL, enabling bookmarking, sharing, and caching.

The POST method is used for actions where data is sent to the server, and the response contains an entity describing or containing the result of the action.

**Example:** When a client sends a GET request for a customer resource, the request start line specifies method GET, URI /customer/123, and protocol version HTTP/1.1.

## Understanding Response Status Categories  *(8 min)*

**Definition:** A response is sent to the client by the server, starting with a protocol version, a status code, and optionally a reason phrase.

Standard 2xx responses indicate successful HTTP requests. A 4xx status code is for situations in which an error seems to have been caused by the client. A 5xx status code indicates that the server is aware that it has encountered an error or is otherwise incapable of performing the request.

## Worked Examples of Requests and Responses  *(5 min)*

**Example:** For a successful GET request, the server returns a 200 status code where the response contains an entity corresponding to the requested resource. For a POST request, the response contains an entity describing or containing the result of the action.

## Practical Application Activity  *(6 min)*

Apply your knowledge by categorizing various HTTP transactions based on methods and status codes.

### Activity: Analyze HTTP Transactions (6 min)

Examine a set of sample HTTP transaction logs. Identify whether each transaction uses a GET or POST method and categorize their return codes into 2xx, 4xx, or 5xx status categories. Analyze the following 6 sample transactions: 1. GET /index.html 200, 2. POST /submit 201, 3. GET /missing 404, 4. POST /update 400, 5. GET /error 500, 6. POST /fail 503.

## Knowledge Check  *(3 min)*

Answer the following questions to check your understanding of HTTP methods and status categories.

**Q1. The GET method is intended to modify the server's state.**

- True
- False

**Q2. Which status code category indicates an error caused by the client?**

- 2xx
- 4xx
- 5xx
- 1xx

## Final Assessment  *(3 min)*

Complete the final assessment questions to demonstrate your mastery of HTTP requests and responses.

**Q3. A client application attempts to fetch a user profile using a URL, but receives a 500-range status code back from the server. Based on this, how should you explain the outcome?**

- The server encountered an internal error or is incapable of performing the request.
- The client submitted an invalid URL.
- The request was successful.
- The client needs to send a POST method instead.

**Q4. Why is GET preferred over POST when retrieving data without modifying state?**

- Because GET requests can be addressed through a URL, enabling bookmarking, sharing, and caching.
- Because POST cannot transmit data.
- Because GET modifies the server state securely.
- Because POST requests are always faster.

## Lesson Summary  *(2 min)*

You have reviewed how GET and POST methods function and how to distinguish between 2xx, 4xx, and 5xx response status categories.

## Answer key

1. (check) **False** - GET requests should only retrieve data and not modify state.
2. (check) **4xx** - A 4xx status code is for situations where an error seems to have been caused by the client.
3. (final) **The server encountered an internal error or is incapable of performing the request.** - 5xx status codes indicate that the server is aware that it has encountered an error or is otherwise incapable of performing the request.
4. (final) **Because GET requests can be addressed through a URL, enabling bookmarking, sharing, and caching.** - GET is preferred for retrieving without making changes as it can be addressed through a URL, enabling bookmarking, sharing, and caching.

## Supplementary videos (optional, not part of the 45 minutes)

- [The Http and the Web | Http Explained | Request-Response Cycle](https://www.youtube.com/watch?v=eesqK59rhGA) (9 min)
- [HTTP crash course | http Methods | http headers](https://www.youtube.com/watch?v=qgZiUvV41TI) (24 min)
- [31 HTTP Request Response structure](https://www.youtube.com/watch?v=rZNdo9UjF94) (14 min)

## References

- [HTTP (Wikipedia)](https://en.wikipedia.org/wiki/HTTP) - retrieved 2026-11-07
- [List of HTTP status codes (Wikipedia)](https://en.wikipedia.org/wiki/List_of_HTTP_status_codes) - retrieved 2026-11-07

**Further reading (books; content not reviewed by the tool)**

- [HTTP (1997)](https://openlibrary.org/works/OL16026044W) - David Gourley, Brian Totty, Linda Mui
- [JavaScript (1996)](https://openlibrary.org/works/OL1643770W) - David Flanagan
- [Het Achterhuis (1944)](https://openlibrary.org/works/OL266178W) - Anne Frank

**Videos**

- [The Http and the Web | Http Explained | Request-Response Cycle](https://www.youtube.com/watch?v=eesqK59rhGA) - The TechCave
- [HTTP crash course | http Methods | http headers](https://www.youtube.com/watch?v=qgZiUvV41TI) - Chai aur Code
- [31 HTTP Request Response structure](https://www.youtube.com/watch?v=rZNdo9UjF94) - Chai aur Code

