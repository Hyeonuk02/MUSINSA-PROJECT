package poc.order.requestlog

import jakarta.servlet.ReadListener
import jakarta.servlet.ServletInputStream
import jakarta.servlet.http.HttpServletRequest
import jakarta.servlet.http.HttpServletRequestWrapper
import java.io.BufferedReader
import java.io.ByteArrayInputStream
import java.io.InputStreamReader
import java.nio.charset.Charset

/** 미리 읽어 둔 원시 요청 본문을 다시 읽을 수 있게 제공하는 래퍼. Phase 3.5-v1.4: Java → Kotlin 전환. */
internal class CachedBodyRequest(request: HttpServletRequest, private val body: ByteArray) : HttpServletRequestWrapper(request) {

    override fun getInputStream(): ServletInputStream {
        val input = ByteArrayInputStream(body)
        return object : ServletInputStream() {
            override fun read(): Int = input.read()

            override fun read(b: ByteArray, off: Int, len: Int): Int = input.read(b, off, len)

            override fun isFinished(): Boolean = input.available() == 0

            override fun isReady(): Boolean = true

            override fun setReadListener(listener: ReadListener) = throw UnsupportedOperationException()
        }
    }

    override fun getReader(): BufferedReader {
        val charset = characterEncoding?.let { Charset.forName(it) } ?: Charsets.UTF_8
        return BufferedReader(InputStreamReader(inputStream, charset))
    }
}
