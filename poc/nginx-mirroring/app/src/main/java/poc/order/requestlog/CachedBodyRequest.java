package poc.order.requestlog;

import jakarta.servlet.ReadListener;
import jakarta.servlet.ServletInputStream;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletRequestWrapper;

import java.io.BufferedReader;
import java.io.ByteArrayInputStream;
import java.io.InputStreamReader;
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;

/** 미리 읽어 둔 원시 요청 본문을 다시 읽을 수 있게 제공하는 래퍼. */
class CachedBodyRequest extends HttpServletRequestWrapper {

    private final byte[] body;

    CachedBodyRequest(HttpServletRequest request, byte[] body) {
        super(request);
        this.body = body;
    }

    @Override
    public ServletInputStream getInputStream() {
        ByteArrayInputStream in = new ByteArrayInputStream(body);
        return new ServletInputStream() {
            @Override
            public int read() {
                return in.read();
            }

            @Override
            public int read(byte[] b, int off, int len) {
                return in.read(b, off, len);
            }

            @Override
            public boolean isFinished() {
                return in.available() == 0;
            }

            @Override
            public boolean isReady() {
                return true;
            }

            @Override
            public void setReadListener(ReadListener listener) {
                throw new UnsupportedOperationException();
            }
        };
    }

    @Override
    public BufferedReader getReader() {
        String encoding = getCharacterEncoding();
        Charset charset = encoding == null ? StandardCharsets.UTF_8 : Charset.forName(encoding);
        return new BufferedReader(new InputStreamReader(getInputStream(), charset));
    }
}
