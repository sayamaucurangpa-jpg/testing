<?php
// Penyaji file yang aman: hanya nama hasil random dari server yang diterima.
const STORAGE = __DIR__ . '/../storage/uploads/';

$f = $_GET['f'] ?? '';

if (!is_string($f) || !preg_match('/^[a-f0-9]{32}\.(png|jpg)$/', $f)) {
    http_response_code(400);
    exit('Bad request');
}

$path = STORAGE . $f;
if (!is_file($path)) {
    http_response_code(404);
    exit('Not found');
}

$mime = (new finfo(FILEINFO_MIME_TYPE))->file($path);
if (!in_array($mime, ['image/png', 'image/jpeg'], true)) {
    http_response_code(415);
    exit('Unsupported');
}

header('Content-Type: ' . $mime);
header('Content-Length: ' . filesize($path));
header('X-Content-Type-Options: nosniff');
header('Content-Disposition: inline; filename="' . $f . '"');
readfile($path);
