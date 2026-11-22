import SwiftUI
import UIKit

struct IntakeCamera: UIViewControllerRepresentable {
    let onCapture: (Data?) -> Void
    let onCancel: () -> Void

    func makeUIViewController(context: Context) -> UIImagePickerController {
        let picker = UIImagePickerController()
        picker.sourceType = .camera
        picker.delegate = context.coordinator
        return picker
    }

    func updateUIViewController(_ controller: UIImagePickerController, context: Context) {}

    func makeCoordinator() -> Coordinator { Coordinator(camera: self) }

    final class Coordinator: NSObject, UIImagePickerControllerDelegate, UINavigationControllerDelegate {
        let camera: IntakeCamera

        init(camera: IntakeCamera) { self.camera = camera }

        func imagePickerController(_ picker: UIImagePickerController,
                                   didFinishPickingMediaWithInfo info: [UIImagePickerController.InfoKey: Any]) {
            guard let image = info[.originalImage] as? UIImage else {
                camera.onCapture(nil)
                return
            }

            // Draw in the camera image's displayed orientation before handing it to ImageIO.
            let ratio = min(1, CGFloat(ImagePreparation.maximumDimension) / max(image.size.width, image.size.height))
            let size = CGSize(width: max(1, floor(image.size.width * ratio)),
                              height: max(1, floor(image.size.height * ratio)))
            let format = UIGraphicsImageRendererFormat()
            format.scale = 1
            let data = UIGraphicsImageRenderer(size: size, format: format).jpegData(withCompressionQuality: 1) { _ in
                image.draw(in: CGRect(origin: .zero, size: size))
            }
            camera.onCapture(data)
        }

        func imagePickerControllerDidCancel(_ picker: UIImagePickerController) { camera.onCancel() }
    }
}
