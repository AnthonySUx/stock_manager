import Foundation
import ImageIO
import UniformTypeIdentifiers

struct PreparedIntakeImage: Sendable {
    let jpeg: Data
}

enum ImagePreparation {
    static let maximumDimension = 1_600
    static let maximumBytes = 5 * 1_024 * 1_024

    enum Failure: Error {
        case unreadable
        case tooLarge
    }

    static func prepare(_ data: Data) throws -> PreparedIntakeImage {
        guard let source = CGImageSourceCreateWithData(data as CFData, nil) else { throw Failure.unreadable }
        let options: [CFString: Any] = [
            kCGImageSourceCreateThumbnailFromImageAlways: true,
            kCGImageSourceCreateThumbnailWithTransform: true,
            kCGImageSourceThumbnailMaxPixelSize: maximumDimension
        ]
        guard let image = CGImageSourceCreateThumbnailAtIndex(source, 0, options as CFDictionary) else {
            throw Failure.unreadable
        }
        var jpeg = try encodeJPEG(image, quality: 0.8)
        if jpeg.count > maximumBytes { jpeg = try encodeJPEG(image, quality: 0.55) }
        guard jpeg.count <= maximumBytes else { throw Failure.tooLarge }
        return .init(jpeg: jpeg)
    }

    private static func encodeJPEG(_ image: CGImage, quality: Double) throws -> Data {
        let data = NSMutableData()
        guard let destination = CGImageDestinationCreateWithData(data, UTType.jpeg.identifier as CFString, 1, nil) else {
            throw Failure.unreadable
        }
        // Encode only the oriented pixels, without copying any source metadata.
        CGImageDestinationAddImage(destination, image,
                                   [kCGImageDestinationLossyCompressionQuality: quality] as CFDictionary)
        guard CGImageDestinationFinalize(destination) else { throw Failure.unreadable }
        return data as Data
    }
}
