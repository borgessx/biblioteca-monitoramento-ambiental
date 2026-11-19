DROP DATABASE IF EXISTS monitoramento_bd;
CREATE DATABASE monitoramento_bd;
USE monitoramento_bd;

CREATE TABLE ambiente (
id INT AUTO_INCREMENT PRIMARY KEY,
nome VARCHAR(100) NOT NULL,
localizacao VARCHAR(150),
descricao TEXT,
ativo BOOLEAN DEFAULT TRUE
);

CREATE TABLE indicador(
id INT AUTO_INCREMENT PRIMARY KEY,
nome VARCHAR(100) NOT NULL,
campo VARCHAR(50) NOT NULL UNIQUE,
unidade VARCHAR(50),
descricao VARCHAR(255)
);

CREATE TABLE sensor(
id INT AUTO_INCREMENT PRIMARY KEY,
id_ambiente INT NOT NULL,
nome VARCHAR(100),
modelo VARCHAR(50),
codigo VARCHAR(50) NOT NULL UNIQUE,
ativo BOOLEAN default TRUE,
data_instalacao DATETIME,
FOREIGN KEY (id_ambiente) REFERENCES ambiente(id)
);

CREATE TABLE limite(
id INT AUTO_INCREMENT PRIMARY KEY,
id_ambiente INT NOT NULL,
id_indicador INT NOT NULL,
valor_minimo DECIMAL(10,2),
valor_maximo DECIMAL(10,2),
gravidade VARCHAR(30),
ativo BOOLEAN DEFAULT TRUE,
FOREIGN KEY (id_ambiente) REFERENCES ambiente(id),
FOREIGN KEY (id_indicador) REFERENCES indicador(id)
);

CREATE TABLE medicao(
id BIGINT AUTO_INCREMENT PRIMARY KEY,
id_sensor INT NOT NULL unique,
temperature DECIMAL(10,2),
humidity DECIMAL(10,2),
CO2 DECIMAL(10,2),
particula1 DECIMAL(10,2),
particula2 DECIMAL(10,2),
registro_tempo DATETIME NOT NULL UNIQUE,
FOREIGN KEY (id_sensor) REFERENCES sensor(id)
);

CREATE TABLE ocorrencia(
id INT AUTO_INCREMENT PRIMARY KEY,
id_medicao BIGINT NOT NULL,
id_limite INT NOT NULL,
valor_registrado DECIMAL(10,2),
statuss VARCHAR(30),
data_abertura DATETIME,
data_encerramento DATETIME
);

CREATE TABLE notificacao(
id INT AUTO_INCREMENT PRIMARY KEY,
id_ocorrencia INT NOT NULL,
destinatario VARCHAR(150),
mensagem VARCHAR(500),
status_envio VARCHAR(30),
data_envio DATETIME,
FOREIGN KEY (id_ocorrencia) REFERENCES ocorrencia(id)
);

CREATE INDEX idx_medicao_registro_tempo ON medicao (registro_tempo);