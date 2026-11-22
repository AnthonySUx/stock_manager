import ImageIO
import UniformTypeIdentifiers
import XCTest
@testable import StockManager

final class ImagePreparationTests: XCTestCase {
    func testPhotoPreparationOrientsResizesAndStripsGPS() throws {
        let context = try XCTUnwrap(CGContext(data: nil, width: 2_000, height: 1_000, bitsPerComponent: 8,
                                             bytesPerRow: 0, space: CGColorSpaceCreateDeviceRGB(),
                                             bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue))
        context.setFillColor(red: 0.2, green: 0.5, blue: 0.7, alpha: 1)
        context.fill(CGRect(x: 0, y: 0, width: 2_000, height: 1_000))
        let image = try XCTUnwrap(context.makeImage())
        let fixture = NSMutableData()
        let destination = try XCTUnwrap(CGImageDestinationCreateWithData(fixture, UTType.jpeg.identifier as CFString, 1, nil))
        let metadata: [CFString: Any] = [
            kCGImagePropertyOrientation: CGImagePropertyOrientation.right.rawValue,
            kCGImagePropertyGPSDictionary: [
                kCGImagePropertyGPSLatitude: 35.0, kCGImagePropertyGPSLatitudeRef: "N"
            ],
            kCGImagePropertyExifDictionary: [kCGImagePropertyExifDateTimeOriginal: "2026:11:20 09:15:00"]
        ]
        CGImageDestinationAddImage(destination, image, metadata as CFDictionary)
        XCTAssertTrue(CGImageDestinationFinalize(destination))
        let original = try XCTUnwrap(CGImageSourceCreateWithData(fixture, nil))
        let originalProperties = try XCTUnwrap(CGImageSourceCopyPropertiesAtIndex(original, 0, nil) as? [CFString: Any])
        XCTAssertNotNil(originalProperties[kCGImagePropertyGPSDictionary])

        let result = try ImagePreparation.prepare(fixture as Data)
        XCTAssertEqual(result.captureDate, "2026-11-20")
        XCTAssertLessThanOrEqual(result.jpeg.count, ImagePreparation.maximumBytes)
        let encoded = try XCTUnwrap(CGImageSourceCreateWithData(result.jpeg as CFData, nil))
        XCTAssertEqual(CGImageSourceGetType(encoded) as String?, UTType.jpeg.identifier)
        let pixels = try XCTUnwrap(CGImageSourceCreateImageAtIndex(encoded, 0, nil))
        XCTAssertEqual(pixels.width, 800)
        XCTAssertEqual(pixels.height, 1_600)
        let properties = try XCTUnwrap(CGImageSourceCopyPropertiesAtIndex(encoded, 0, nil) as? [CFString: Any])
        XCTAssertNil(properties[kCGImagePropertyGPSDictionary])
        let exif = properties[kCGImagePropertyExifDictionary] as? [CFString: Any]
        XCTAssertNil(exif?[kCGImagePropertyExifDateTimeOriginal])
    }

    func testPhotoPreparationRejectsUnreadableData() {
        XCTAssertThrowsError(try ImagePreparation.prepare(Data("not an image".utf8)))
    }
}
