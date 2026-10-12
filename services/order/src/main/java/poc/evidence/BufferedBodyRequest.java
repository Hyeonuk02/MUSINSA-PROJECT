package poc.evidence;

import jakarta.servlet.ReadListener;
import jakarta.servlet.ServletInputStream;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletRequestWrapper;

import java.io.BufferedReader;
import java.io.ByteArrayInputStream;
import java.io.InputStreamReader;
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;

/**
 * 필터가 미리 다 읽은 요청 본문을 뒤쪽에서 다시 읽을 수 있게 하는 래퍼.
 *
 * <p>ContentCachingRequestWrapper는 뒤쪽이 실제로 읽은 만큼만 캐시한다. 앱이 본문을 읽지 않거나
 * 중간에 실패하면 bodyHash가 "받은 요청"이 아니라 "앱이 읽은 부분"의 해시가 된다.
 * request.bodyHash는 Legacy/New가 같은 요청을 받았다는 증거이므로 받은 바이트 전부로 계산한다.
 */
class BufferedBodyRequest extends HttpServletRequestWrapper {

    private final byte[] body;

    BufferedBodyRequest(HttpServletRequest request, byte[] body) {
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
