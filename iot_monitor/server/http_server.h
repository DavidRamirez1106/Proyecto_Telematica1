#ifndef HTTP_SERVER_H
#define HTTP_SERVER_H

#include <string>
#include <map>
#include <functional>
#include <thread>
#include <atomic>

/* =========================================================
   HttpServer — Servidor HTTP básico (RFC 7230 simplificado)
   Maneja peticiones GET, interpreta cabeceras,
   devuelve códigos de estado HTTP correctos.
   Se ejecuta en su propio hilo.
   ========================================================= */

struct HttpRequest {
    std::string method;          // GET, POST, etc.
    std::string path;            // /index.html, /api/status, etc.
    std::string http_version;    // HTTP/1.0 o HTTP/1.1
    std::map<std::string, std::string> headers;
    std::string body;
};

struct HttpResponse {
    int         status_code;     // 200, 404, 401, 500...
    std::string status_text;     // OK, Not Found, ...
    std::map<std::string, std::string> headers;
    std::string body;

    HttpResponse(int code = 200, const std::string& text = "OK")
        : status_code(code), status_text(text) {}
};

// Tipo de handler: función que recibe request y devuelve response
using RouteHandler = std::function<HttpResponse(const HttpRequest&)>;

class HttpServer {
public:
    HttpServer(int port, const std::string& web_root);
    ~HttpServer();

    // Registra una ruta dinámica (ej: /api/status)
    void add_route(const std::string& path, RouteHandler handler);

    // Inicia el servidor en un hilo separado
    void start();

    // Detiene el servidor
    void stop();

private:
    int         port_;
    std::string web_root_;
    int         server_fd_;
    std::atomic<bool> running_;
    std::thread server_thread_;

    std::map<std::string, RouteHandler> routes_;

    void listen_loop();
    void handle_client(int client_fd,
                       const std::string& client_ip,
                       int client_port);

    HttpRequest  parse_request(const std::string& raw);
    std::string  build_response(const HttpResponse& resp);
    HttpResponse serve_file(const std::string& path);
    HttpResponse not_found();
    HttpResponse method_not_allowed();
    std::string  mime_type(const std::string& ext);
    std::string  read_file(const std::string& filepath);
    bool         file_exists(const std::string& filepath);
};

// Helpers para construir respuestas rápidas
HttpResponse http_ok(const std::string& body,
                     const std::string& content_type = "text/html");
HttpResponse http_json(const std::string& json_body);
HttpResponse http_error(int code, const std::string& text,
                        const std::string& detail = "");

#endif // HTTP_SERVER_H
