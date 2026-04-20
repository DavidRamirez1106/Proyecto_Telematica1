# Makefile — Servidor SIMP
# Uso en EC2:  make        (compila)
#              make clean  (limpia binarios)
#              make run    (compila y ejecuta con valores de ejemplo)

CXX      := g++
CXXFLAGS := -std=c++17 -Wall -Wextra -pthread -O2
TARGET   := server
SRCS     := server.cpp logger.cpp http_server.cpp
OBJS     := $(SRCS:.cpp=.o)

# Puerto y archivo de log por defecto (se puede sobreescribir)
PORT     ?= 9000
LOGFILE  ?= server.log

.PHONY: all clean run install-deps

all: $(TARGET)

$(TARGET): $(OBJS)
	$(CXX) $(CXXFLAGS) -o $@ $^
	@echo ""
	@echo "  Compilacion exitosa: ./$(TARGET)"
	@echo "  Uso: ./$(TARGET) <puerto> <archivo_de_logs>"
	@echo ""

%.o: %.cpp
	$(CXX) $(CXXFLAGS) -c $< -o $@

run: all
	./$(TARGET) $(PORT) $(LOGFILE)

clean:
	rm -f $(OBJS) $(TARGET) *.log

# Instalar dependencias en Ubuntu/Amazon Linux (ejecutar como root o con sudo)
install-deps:
	apt-get update && apt-get install -y g++ make
	@echo "Dependencias instaladas."
